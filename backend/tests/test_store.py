"""Capacity and concurrency regression tests for temporary storage."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.schemas.items import ItemCreate
from app.services.items import ItemStore, StoreFullError


class StoreTests(unittest.TestCase):
    def report(self):
        return ItemCreate(title="Black Wallet", description="Black leather wallet",
                          category="accessories", location="Library", type="found",
                          reported_by="Student")

    def test_capacity_and_recovery(self):
        store = ItemStore(capacity=1)
        first = store.create(self.report())
        with self.assertRaises(StoreFullError):
            store.create(self.report())
        store.delete(first.id)
        self.assertGreater(store.create(self.report()).id, first.id)

    def test_concurrent_creation_and_copy_isolation(self):
        store = ItemStore()
        with ThreadPoolExecutor(max_workers=8) as workers:
            reports = list(workers.map(lambda _: store.create(self.report()), range(50)))
        self.assertEqual(len({item.id for item in reports}), 50)
        reports[0].title = "Changed by caller"
        self.assertEqual(store.get(reports[0].id).title, "Black Wallet")
