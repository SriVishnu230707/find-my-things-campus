"""Public normalized photos and owner/staff-only upload/removal."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from app.auth import CurrentUser
from app.database import get_session
from app.models.media import ItemPhoto
from app.routers.items import ItemID
from app.schemas.items import ItemRead
from app.services.media import MAX_UPLOAD_BYTES, change_photo

router = APIRouter(tags=["Photos"])
DB = Annotated[Session, Depends(get_session)]


@router.put("/items/{item_id}/photo", response_model=ItemRead)
def upload_photo(
    item_id: ItemID,
    user: CurrentUser,
    session: DB,
    photo: Annotated[UploadFile, File()],
):
    try:
        return change_photo(
            session,
            item_id,
            user,
            photo.file.read(MAX_UPLOAD_BYTES + 1),
            photo.content_type,
        )
    finally:
        photo.file.close()


@router.get("/items/{item_id}/photo")
def get_photo(item_id: ItemID, session: DB):
    photo = session.get(ItemPhoto, item_id)
    if photo is None:
        raise HTTPException(404, "Photo not found")
    return Response(
        photo.data,
        media_type="image/jpeg",
        headers={"Content-Disposition": 'inline; filename="report-photo.jpg"'},
    )


@router.delete("/items/{item_id}/photo", response_model=ItemRead)
def remove_photo(item_id: ItemID, user: CurrentUser, session: DB):
    return change_photo(session, item_id, user)
