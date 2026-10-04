"""Transactional report operations using a request-scoped session."""
from datetime import datetime, timezone
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session
from app.models.items import Item
from app.schemas.items import ItemCreate, ItemRead, ItemUpdate

class ItemRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, data: ItemCreate) -> ItemRead:
        now = datetime.now(timezone.utc)
        item = Item(**data.model_dump(), status="open", created_at=now, updated_at=now)
        self.session.add(item)
        self.session.flush()
        result = ItemRead.model_validate(item)
        self.session.commit()
        return result

    def list(self, limit: int = 100, offset: int = 0) -> list[ItemRead]:
        statement = select(Item).order_by(Item.id).offset(offset).limit(limit)
        return [ItemRead.model_validate(item) for item in self.session.scalars(statement)]

    def get(self, item_id: int) -> ItemRead | None:
        item = self.session.get(Item, item_id)
        return ItemRead.model_validate(item) if item else None

    def update(self, item_id: int, changes: ItemUpdate) -> ItemRead | None:
        # Only supplied columns change, avoiding stale snapshots of other fields.
        statement = update(Item).where(Item.id == item_id).values(
            **changes.model_dump(exclude_unset=True), updated_at=datetime.now(timezone.utc)
        ).returning(Item)
        item = self.session.scalars(statement).first()
        result = ItemRead.model_validate(item) if item else None
        self.session.commit()
        return result

    def delete(self, item_id: int) -> bool:
        result = self.session.execute(delete(Item).where(Item.id == item_id).returning(Item.id))
        deleted = result.scalar_one_or_none() is not None
        self.session.commit()
        return deleted
