"""Private claims with database-enforced active and winning uniqueness."""

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.items import UTCDateTime


class Claim(Base):
    __tablename__ = "claims"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','approved','rejected','withdrawn','completed')",
            name="ck_claims_status",
        ),
        CheckConstraint(
            "length(evidence) BETWEEN 10 AND 2000", name="ck_claims_evidence"
        ),
        Index("ix_claims_item_id", "item_id"),
        Index("ix_claims_claimant_id", "claimant_id"),
        Index(
            "uq_claims_active_student",
            "item_id",
            "claimant_id",
            unique=True,
            sqlite_where=text("status IN ('pending','approved')"),
            postgresql_where=text("status IN ('pending','approved')"),
        ),
        Index(
            "uq_claims_winner",
            "item_id",
            unique=True,
            sqlite_where=text("status IN ('approved','completed')"),
            postgresql_where=text("status IN ('approved','completed')"),
        ),
        {"sqlite_autoincrement": True},
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="RESTRICT"))
    claimant_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    evidence: Mapped[str] = mapped_column(String(2000))
    status: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime())
