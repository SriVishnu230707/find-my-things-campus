"""Private inbox with recipient-scoped read operations."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.auth import CurrentUser
from app.database import get_session
from app.models.notifications import Notification
from app.routers.items import ItemID
from app.schemas.notifications import NotificationRead, ReadAllResult, UnreadCount

router = APIRouter(prefix="/notifications", tags=["Notifications"])
DB = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[NotificationRead])
def inbox(
    user: CurrentUser,
    session: DB,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0, le=2**63 - 1)] = 0,
    unread_only: bool = False,
):
    query = select(Notification).where(Notification.recipient_id == user.id)
    if unread_only:
        query = query.where(Notification.is_read.is_(False))
    return list(
        session.scalars(
            query.order_by(Notification.id.desc()).limit(limit).offset(offset)
        )
    )


@router.get("/unread-count", response_model=UnreadCount)
def unread_count(user: CurrentUser, session: DB):
    return {
        "unread_count": session.scalar(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.recipient_id == user.id, Notification.is_read.is_(False)
            )
        )
    }


@router.post("/read-all", response_model=ReadAllResult)
def read_all(user: CurrentUser, session: DB):
    result = session.execute(
        update(Notification)
        .where(Notification.recipient_id == user.id, Notification.is_read.is_(False))
        .values(is_read=True)
    )
    session.commit()
    return {"updated": result.rowcount}


@router.patch("/{notification_id}/read", response_model=NotificationRead)
def mark_read(notification_id: ItemID, user: CurrentUser, session: DB):
    notification = session.scalar(
        update(Notification)
        .where(Notification.id == notification_id, Notification.recipient_id == user.id)
        .values(is_read=True)
        .returning(Notification)
    )
    if notification is None:
        raise HTTPException(404, "Notification not found")
    result = NotificationRead.model_validate(notification)
    session.commit()
    return result
