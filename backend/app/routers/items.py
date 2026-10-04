"""Lost-and-found report endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status

from app.schemas.items import ItemCreate, ItemRead, ItemUpdate
from sqlalchemy.orm import Session
from app.database import get_session
from app.services.items import ItemRepository

router = APIRouter(prefix="/items", tags=["Reports"])
ItemID = Annotated[int, Path(gt=0, le=2**63 - 1)]


def get_store(session: Annotated[Session, Depends(get_session)]) -> ItemRepository:
    return ItemRepository(session)


Store = Annotated[ItemRepository, Depends(get_store)]


@router.post("", response_model=ItemRead, status_code=status.HTTP_201_CREATED)
def create_item(data: ItemCreate, store: Store, response: Response) -> ItemRead:
    item = store.create(data)
    response.headers["Location"] = f"/items/{item.id}"
    return item


@router.get("", response_model=list[ItemRead])
def list_items(store: Store, limit: Annotated[int, Query(ge=1, le=100)] = 100,
               offset: Annotated[int, Query(ge=0, le=2**63 - 1)] = 0) -> list[ItemRead]:
    return store.list(limit, offset)


@router.get("/{item_id}", response_model=ItemRead)
def get_item(item_id: ItemID, store: Store) -> ItemRead:
    item = store.get(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.patch("/{item_id}", response_model=ItemRead)
def update_item(item_id: ItemID, data: ItemUpdate, store: Store) -> ItemRead:
    item = store.update(item_id, data)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: ItemID, store: Store) -> Response:
    if not store.delete(item_id):
        raise HTTPException(status_code=404, detail="Item not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
