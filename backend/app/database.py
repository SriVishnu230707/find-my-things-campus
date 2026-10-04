"""Shared database configuration for the API and Alembic."""
import os
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session

class Base(DeclarativeBase):
    pass

def database_url() -> str:
    default = Path(__file__).resolve().parents[1] / "data" / "campus.db"
    return os.environ.get("DATABASE_URL", f"sqlite:///{default.as_posix()}")

def build_engine(url: str):
    parsed = make_url(url)
    options = {"pool_pre_ping": True}
    if parsed.get_backend_name() == "sqlite":
        if parsed.database and parsed.database != ":memory:":
            Path(parsed.database).resolve().parent.mkdir(parents=True, exist_ok=True)
        options["connect_args"] = {"check_same_thread": False, "timeout": 5}
    engine = create_engine(url, **options)
    if parsed.get_backend_name() == "sqlite":
        @event.listens_for(engine, "connect")
        def configure_sqlite(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")
    return engine

engine = build_engine(database_url())

def get_session():
    with Session(engine, expire_on_commit=False) as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise
