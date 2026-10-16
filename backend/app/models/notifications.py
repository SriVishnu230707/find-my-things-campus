"""Recipient-scoped durable notifications; no private evidence in messages."""

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, String, false
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.items import UTCDateTime


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_recipient_read_id", "recipient_id", "is_read", "id"),
        {"sqlite_autoincrement": True},
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    recipient_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"))
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(String(240))
    is_read: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
