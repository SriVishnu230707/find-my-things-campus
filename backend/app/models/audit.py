"""Moderation history stores identifiers and actions, not passwords or evidence."""

from datetime import datetime

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.items import UTCDateTime


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_created_id", "created_at", "id"),
        {"sqlite_autoincrement": True},
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None]
    actor_role: Mapped[str] = mapped_column(String(20))
    action: Mapped[str] = mapped_column(String(40))
    item_id: Mapped[int | None]
    claim_id: Mapped[int | None]
    target_user_id: Mapped[int | None]
    details: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
