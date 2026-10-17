"""Real PostgreSQL/Redis integration tests; refuse any non-test database name."""

import os
import secrets
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.database import Base, build_engine, verify_database
from app.models import Claim, Item, ItemPhoto, Notification, User
from app.ops import import_sqlite
from app.schemas.items import ItemCreate
from app.security import hash_password
from app.services.claims import create_claim, transition
from app.services.items import ItemRepository

URL = os.environ.get("CAMPUS_INTEGRATION_DATABASE_URL")
REDIS_URL = os.environ.get("CAMPUS_INTEGRATION_REDIS_URL")
BACKEND = Path(__file__).resolve().parents[1]


@unittest.skipUnless(
    URL and REDIS_URL, "Set explicit disposable PostgreSQL and Redis integration URLs"
)
class InfrastructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if (
            make_url(URL).get_backend_name() != "postgresql"
            or make_url(URL).database != "campus_test"
        ):
            raise RuntimeError(
                "Integration tests require a disposable database named campus_test"
            )
        cls.engine = build_engine(URL)
        cls.addClassCleanup(cls.engine.dispose)
        cls.migrate("upgrade", "head")

    @classmethod
    def migrate(cls, action, target):
        subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                str(BACKEND / "alembic.ini"),
                action,
                target,
            ],
            env={**os.environ, "DATABASE_URL": URL, "APP_ENV": "development"},
            check=True,
            stdout=subprocess.DEVNULL,
        )

    def setUp(self):
        with self.engine.begin() as connection:
            names = ",".join(
                '"' + table.name + '"' for table in Base.metadata.sorted_tables
            )
            connection.exec_driver_sql(
                "TRUNCATE " + names + " RESTART IDENTITY CASCADE"
            )

    def users(self, session):
        now = datetime.now(timezone.utc)
        people = [
            User(
                email=f"{name}@example.org",
                display_name=name,
                password_hash=hash_password("Test-only-password-123"),
                role="student",
                email_verified=True,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            for name in ["Finder", "ClaimantOne", "ClaimantTwo"]
        ]
        session.add_all(people)
        session.commit()
        return [person.id for person in people]

    def test_postgres_schema_constraints_and_concurrent_approval(self):
        from alembic.autogenerate import compare_metadata
        from alembic.migration import MigrationContext
        from fastapi import HTTPException

        verify_database(self.engine)
        with self.engine.connect() as connection:
            self.assertEqual(
                compare_metadata(MigrationContext.configure(connection), Base.metadata),
                [],
            )
        with Session(self.engine) as session:
            ids = self.users(session)
            finder = session.get(User, ids[0])
            item = ItemRepository(session).create(
                ItemCreate(
                    title="Postgres calculator",
                    description="Calculator found near the library",
                    location="Library",
                    category="electronics",
                    type="found",
                ),
                finder,
            )
            claims = [
                create_claim(
                    session,
                    item.id,
                    session.get(User, user_id),
                    "Private identifying evidence",
                )
                for user_id in ids[1:]
            ]

        def approve(claim):
            with Session(self.engine) as session:
                try:
                    transition(session, claim.id, session.get(User, ids[0]), "approved")
                    return 200
                except HTTPException as error:
                    session.rollback()
                    return error.status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(approve, claims)), [200, 409])
        with Session(self.engine) as session:
            winner = session.scalar(select(Claim).where(Claim.status == "approved"))
            transition(session, winner.id, session.get(User, ids[0]), "completed")
            self.assertEqual(session.get(Item, item.id).status, "resolved")
            self.assertEqual(
                sorted(session.scalars(select(Claim.status))), ["completed", "rejected"]
            )
            self.assertEqual(len(list(session.scalars(select(Notification)))), 5)

    def test_sqlite_import_preserves_data_photos_and_deleted_id_sequence(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "source.db"
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "alembic",
                    "-c",
                    str(BACKEND / "alembic.ini"),
                    "upgrade",
                    "head",
                ],
                env={
                    **os.environ,
                    "DATABASE_URL": "sqlite:///" + source_path.as_posix(),
                },
                check=True,
                stdout=subprocess.DEVNULL,
            )
            source = build_engine("sqlite:///" + source_path.as_posix())
            try:
                with Session(source) as session:
                    ids = self.users(session)
                    report = ItemRepository(session).create(
                        ItemCreate(
                            title="Imported wallet",
                            description="Black leather wallet found in library",
                            location="Library",
                            category="accessories",
                            type="found",
                        ),
                        session.get(User, ids[0]),
                    )
                    removed = ItemRepository(session).create(
                        ItemCreate(
                            title="Deleted wallet",
                            description="Temporary report to preserve its ID",
                            location="Library",
                            category="accessories",
                            type="lost",
                        ),
                        session.get(User, ids[0]),
                    )
                    ItemRepository(session).delete(
                        removed.id, session.get(User, ids[0])
                    )
                    session.add(ItemPhoto(item_id=report.id, data=b"test-photo-bytes"))
                    session.commit()
                self.assertGreater(import_sqlite(source_path, URL), 0)
                with Session(self.engine) as session:
                    self.assertEqual(
                        session.get(ItemPhoto, report.id).data, b"test-photo-bytes"
                    )
                    self.assertEqual(
                        session.get(User, ids[0]).email, "Finder@example.org"
                    )
                    created = ItemRepository(session).create(
                        ItemCreate(
                            title="New report",
                            description="A new report after migration",
                            location="Library",
                            category="other",
                            type="lost",
                        ),
                        session.get(User, ids[0]),
                    )
                    self.assertGreater(created.id, removed.id)
                with self.assertRaises(ValueError):
                    import_sqlite(source_path, URL)
            finally:
                source.dispose()

    def test_shared_redis_limit_is_atomic_between_clients(self):
        import redis

        from app.auth_limits import SLIDING_WINDOW

        first, second = redis.Redis.from_url(REDIS_URL), redis.Redis.from_url(REDIS_URL)
        key = "campus:test:" + secrets.token_hex(16)
        try:

            def attempt(index):
                client = first if index % 2 else second
                return int(
                    client.eval(SLIDING_WINDOW, 1, key, 5, 60000, secrets.token_hex(16))
                )

            with ThreadPoolExecutor(max_workers=10) as pool:
                self.assertEqual(sum(pool.map(attempt, range(20))), 5)
            self.assertGreater(first.pttl(key), 0)
            self.assertLessEqual(first.zcard(key), 5)
        finally:
            first.delete(key)
            first.close()
            second.close()

    def test_postgres_migration_roundtrip(self):
        self.migrate("downgrade", "base")
        self.migrate("upgrade", "head")
        verify_database(self.engine)
