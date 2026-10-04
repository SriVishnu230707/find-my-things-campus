"""Database constraints, rollback, concurrency, and migration regression tests."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.database import build_engine
from app.schemas.items import ItemCreate
from app.services.items import ItemRepository

class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.url = 'sqlite:///' + (Path(self.directory.name) / 'test.db').as_posix()
        self.environment = {**os.environ, 'DATABASE_URL': self.url}
        self.migrate('upgrade', 'head')
        self.engine = build_engine(self.url)
        self.addCleanup(self.engine.dispose)

    def migrate(self, action, target):
        subprocess.run([sys.executable, '-m', 'alembic', '-c',
                        str(Path(__file__).resolve().parents[1] / 'alembic.ini'),
                        action, target], env=self.environment, check=True,
                       stdout=subprocess.DEVNULL)

    def report(self):
        return ItemCreate(title='Black Wallet', description='Black leather wallet',
                          category='accessories', location='Library', type='found',
                          reported_by='Student')

    def test_constraints_rollback_and_recovery(self):
        with Session(self.engine) as session:
            repo = ItemRepository(session)
            item = repo.create(self.report())
            with self.assertRaises(IntegrityError):
                session.execute(text("UPDATE items SET status = 'invalid' WHERE id = :id"), {'id': item.id})
            session.rollback()
            self.assertEqual(repo.get(item.id).status, 'open')
            self.assertGreater(repo.create(self.report()).id, item.id)

    def test_concurrent_creation_and_result_isolation(self):
        def create(_):
            with Session(self.engine) as session:
                return ItemRepository(session).create(self.report())
        with ThreadPoolExecutor(max_workers=8) as workers:
            reports = list(workers.map(create, range(50)))
        self.assertEqual(len({item.id for item in reports}), 50)
        reports[0].title = 'Changed by caller'
        with Session(self.engine) as session:
            self.assertEqual(ItemRepository(session).get(reports[0].id).title, 'Black Wallet')

    def test_migration_roundtrip_and_metadata(self):
        from alembic.autogenerate import compare_metadata
        from alembic.migration import MigrationContext
        from app.database import Base
        with self.engine.connect() as connection:
            differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)
            self.assertEqual(differences, [])
        self.migrate('downgrade', 'base')
        self.assertNotIn('items', inspect(self.engine).get_table_names())
        self.migrate('upgrade', 'head')
        self.assertIn('items', inspect(self.engine).get_table_names())

    def test_startup_rejects_stale_revision_and_missing_table(self):
        from app.database import verify_database
        verify_database(self.engine)
        with self.engine.begin() as connection:
            connection.execute(text("UPDATE alembic_version SET version_num = 'unknown'"))
        with self.assertRaises(RuntimeError):
            verify_database(self.engine)
        with self.engine.begin() as connection:
            connection.execute(text("UPDATE alembic_version SET version_num = '0001'"))
            connection.execute(text("DROP TABLE items"))
        from sqlalchemy.exc import SQLAlchemyError
        with self.assertRaises(SQLAlchemyError):
            verify_database(self.engine)
