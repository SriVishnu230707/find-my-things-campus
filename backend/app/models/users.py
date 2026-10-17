"""User identities; roles are never accepted from public registration."""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, Integer, String, false, true
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.items import UTCDateTime


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('student', 'staff')", name="ck_users_role"),
        CheckConstraint(
            "length(display_name) BETWEEN 2 AND 100", name="ck_users_display_name"
        ),
        {"sqlite_autoincrement": True},
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(512))
    role: Mapped[str] = mapped_column(String(10), default="student")
    email_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true()
    )
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    @property
    def campus_verified(self) -> bool:
        from app.account_config import campus_address

        return self.email_verified and campus_address(self.email)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime())
