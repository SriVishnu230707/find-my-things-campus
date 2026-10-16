"""Lost-and-found report endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy.orm import Session

from app.auth import CurrentUser
from app.database import get_session
from app.schemas.items import ItemCreate, ItemQuery, ItemRead, ItemUpdate
from app.services.items import ItemRepository

router = APIRouter(prefix="/items", tags=["Reports"])
ItemID = Annotated[int, Path(gt=0, le=2**63 - 1)]


def get_store(session: Annotated[Session, Depends(get_session)]) -> ItemRepository:
    return ItemRepository(session)


Store = Annotated[ItemRepository, Depends(get_store)]


@router.post("", response_model=ItemRead, status_code=status.HTTP_201_CREATED)
def create_item(
    data: ItemCreate, store: Store, response: Response, user: CurrentUser
) -> ItemRead:
    item = store.create(data, user)
    response.headers["Location"] = f"/items/{item.id}"
    return item


@router.get("", response_model=list[ItemRead])
def list_items(store: Store, filters: Annotated[ItemQuery, Query()]) -> list[ItemRead]:
    """Search title/description and combine filters before sorting and paging."""
    return store.list(filters)


@router.get("/mine", response_model=list[ItemRead])
def my_items(
    store: Store, filters: Annotated[ItemQuery, Query()], user: CurrentUser
) -> list[ItemRead]:
    """Filter by the authenticated owner before pagination."""
    return store.list(filters, owner_id=user.id)


@router.get("/{item_id}", response_model=ItemRead)
def get_item(item_id: ItemID, store: Store) -> ItemRead:
    item = store.get(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.patch("/{item_id}", response_model=ItemRead)
def update_item(
    item_id: ItemID, data: ItemUpdate, store: Store, user: CurrentUser
) -> ItemRead:
    check_permission(item_id, store, user)
    item = store.update(item_id, data, user)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: ItemID, store: Store, user: CurrentUser) -> Response:
    check_permission(item_id, store, user)
    if not store.delete(item_id, user):
        raise HTTPException(status_code=404, detail="Item not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def check_permission(item_id, store, user):
    item = store.get(item_id)
    if item is None:
        raise HTTPException(404, "Item not found")
    if user.role != "staff" and item.reporter_id != user.id:
        raise HTTPException(403, "You may only modify your own reports")


@router.post("/{item_id}/archive", response_model=ItemRead)
def archive_item(item_id: ItemID, store: Store, user: CurrentUser):
    return store.archive(item_id, user)
