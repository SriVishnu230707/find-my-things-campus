"""One normalized photo per report, stored transactionally with its metadata."""

from sqlalchemy import CheckConstraint, ForeignKey, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ItemPhoto(Base):
    __tablename__ = "item_photos"
    __table_args__ = (
        CheckConstraint("length(data) BETWEEN 1 AND 1048576", name="ck_photo_size"),
    )
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    data: Mapped[bytes] = mapped_column(LargeBinary)
