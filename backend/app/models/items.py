"""Persistent report model and database-level constraints."""
from datetime import datetime, timezone
from sqlalchemy import CheckConstraint, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator
from app.database import Base

class UTCDateTime(TypeDecorator):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            if value.tzinfo is None:
                raise ValueError("Timestamp must have a timezone")
            return value.astimezone(timezone.utc)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        return value

class Item(Base):
    __tablename__ = "items"
    __table_args__ = (
        CheckConstraint("type IN ('lost', 'found')", name="ck_items_type"),
        CheckConstraint("status IN ('open', 'resolved')", name="ck_items_status"),
        CheckConstraint("category IN ('electronics', 'clothing', 'documents', 'accessories', 'other')", name="ck_items_category"),
        CheckConstraint("length(title) BETWEEN 3 AND 120", name="ck_items_title"),
        CheckConstraint("length(description) BETWEEN 10 AND 2000", name="ck_items_description"),
        CheckConstraint("length(location) BETWEEN 2 AND 150", name="ck_items_location"),
        CheckConstraint("length(reported_by) BETWEEN 2 AND 100", name="ck_items_reporter"),
        {"sqlite_autoincrement": True},
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(2000))
    category: Mapped[str] = mapped_column(String(20))
    location: Mapped[str] = mapped_column(String(150))
    type: Mapped[str] = mapped_column(String(10))
    reported_by: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime())
