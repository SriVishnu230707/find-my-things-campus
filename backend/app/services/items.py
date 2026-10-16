"""Transactional report operations using a request-scoped session."""

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from app.models.items import Item
from app.models.users import User
from app.schemas.items import ItemCreate, ItemQuery, ItemRead, ItemUpdate
from app.services.claims import has_claims, lock_item, moderator


class ItemRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, data: ItemCreate, reporter: User | None = None) -> ItemRead:
        now = datetime.now(timezone.utc)
        item = Item(
            **data.model_dump(),
            reported_by=reporter.display_name if reporter else "Legacy report",
            reporter_id=reporter.id if reporter else None,
            status="open",
            created_at=now,
            updated_at=now,
        )
        self.session.add(item)
        self.session.flush()
        result = ItemRead.model_validate(item)
        self.session.commit()
        return result

    def list(
        self, filters: ItemQuery | None = None, owner_id: int | None = None
    ) -> list[ItemRead]:
        filters = filters or ItemQuery()
        statement = select(Item).where(Item.archived == filters.archived)
        if owner_id is not None:
            statement = statement.where(Item.reporter_id == owner_id)
        if filters.q is not None:
            statement = statement.where(
                or_(
                    Item.title.icontains(filters.q, autoescape=True),
                    Item.description.icontains(filters.q, autoescape=True),
                )
            )
        if filters.location is not None:
            statement = statement.where(
                Item.location.icontains(filters.location, autoescape=True)
            )
        for name in ("category", "type", "status"):
            value = getattr(filters, name)
            if value is not None:
                statement = statement.where(getattr(Item, name) == value)
        order = (
            (Item.created_at.desc(), Item.id.desc())
            if filters.sort == "newest"
            else (Item.created_at.asc(), Item.id.asc())
        )
        statement = (
            statement.order_by(*order).offset(filters.offset).limit(filters.limit)
        )
        return [
            ItemRead.model_validate(item) for item in self.session.scalars(statement)
        ]

    def get(self, item_id: int) -> ItemRead | None:
        item = self.session.get(Item, item_id)
        return ItemRead.model_validate(item) if item else None

    def update(
        self, item_id: int, changes: ItemUpdate, actor: User | None = None
    ) -> ItemRead | None:
        # Only supplied columns change, avoiding stale snapshots of other fields.
        current = lock_item(self.session, item_id)
        if actor is not None:
            moderator(current, actor)
        if current.archived:
            raise HTTPException(409, "Archived reports cannot be edited")
        if {"type", "status"} & changes.model_fields_set and has_claims(
            self.session, item_id
        ):
            raise HTTPException(
                409, "Use the claim workflow for reports with claim history"
            )
        statement = (
            update(Item)
            .where(Item.id == item_id)
            .values(
                **changes.model_dump(exclude_unset=True),
                updated_at=datetime.now(timezone.utc),
            )
            .returning(Item)
        )
        if actor is not None and actor.role != "staff":
            statement = statement.where(Item.reporter_id == actor.id)
        item = self.session.scalars(statement).first()
        result = ItemRead.model_validate(item) if item else None
        self.session.commit()
        return result

    def delete(self, item_id: int, actor: User | None = None) -> bool:
        # Lock before checking history so a concurrent claim cannot be lost.
        if self.session.get(Item, item_id) is None:
            return False
        current = lock_item(self.session, item_id)
        if actor is not None:
            moderator(current, actor)
        if has_claims(self.session, item_id):
            raise HTTPException(409, "Report has claim history; archive it instead")
        statement = delete(Item).where(Item.id == item_id).returning(Item.id)
        if actor is not None and actor.role != "staff":
            statement = statement.where(Item.reporter_id == actor.id)
        result = self.session.execute(statement)
        deleted = result.scalar_one_or_none() is not None
        self.session.commit()
        return deleted

    def archive(self, item_id, actor):
        item = lock_item(self.session, item_id)
        moderator(item, actor)
        if has_claims(self.session, item_id, active=True):
            raise HTTPException(
                409, "Finish or withdraw active claims before archiving"
            )
        item.archived = True
        item.updated_at = datetime.now(timezone.utc)
        result = ItemRead.model_validate(item)
        self.session.commit()
        return result
