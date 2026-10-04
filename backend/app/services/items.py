"""Thread-safe, process-local storage; replaced by a database in Phase 3."""

from datetime import datetime, timezone
from threading import Lock
from itertools import islice

from app.schemas.items import ItemCreate, ItemRead, ItemUpdate


class StoreFullError(Exception):
    """The temporary store has reached its report limit."""


class ItemStore:
    def __init__(self, capacity: int = 1000) -> None:
        self._items: dict[int, ItemRead] = {}
        self._next_id = 1
        self._lock = Lock()
        self._capacity = capacity

    def create(self, data: ItemCreate) -> ItemRead:
        with self._lock:
            if len(self._items) >= self._capacity:
                raise StoreFullError("Temporary report capacity reached")
            now = datetime.now(timezone.utc)
            item = ItemRead(**data.model_dump(), id=self._next_id,
                            status="open", created_at=now, updated_at=now)
            self._items[item.id] = item
            self._next_id += 1
            return item.model_copy(deep=True)

    def list(self, limit: int = 100, offset: int = 0) -> list[ItemRead]:
        with self._lock:
            return [item.model_copy(deep=True) for item in
                    islice(self._items.values(), offset, offset + limit)]

    def get(self, item_id: int) -> ItemRead | None:
        with self._lock:
            item = self._items.get(item_id)
            return item.model_copy(deep=True) if item else None

    def update(self, item_id: int, changes: ItemUpdate) -> ItemRead | None:
        with self._lock:
            item = self._items.get(item_id)
            if item is None:
                return None
            data = item.model_dump()
            data.update(changes.model_dump(exclude_unset=True))
            data["updated_at"] = datetime.now(timezone.utc)
            updated = ItemRead.model_validate(data)
            self._items[item_id] = updated
            return updated.model_copy(deep=True)

    def delete(self, item_id: int) -> bool:
        with self._lock:
            return self._items.pop(item_id, None) is not None
