"""Single-use email tokens store only SHA-256 digests, never raw secrets."""

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.items import UTCDateTime


class AccountToken(Base):
    __tablename__ = "account_tokens"
    __table_args__ = (
        CheckConstraint(
            "purpose IN ('verify','reset')", name="ck_account_token_purpose"
        ),
        Index(
            "ix_account_tokens_user_purpose_created", "user_id", "purpose", "created_at"
        ),
        {"sqlite_autoincrement": True},
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    purpose: Mapped[str] = mapped_column(String(10))
    digest: Mapped[str] = mapped_column(String(64), unique=True)
    session_version: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
