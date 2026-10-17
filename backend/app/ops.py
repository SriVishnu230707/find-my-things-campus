"""Explicit backup and migration commands; never overwrite a live database."""

import argparse
import os
import sqlite3
from contextlib import closing
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url

import app.models  # noqa: F401 -- register all metadata
from app.database import Base, build_engine, database_url, verify_database


def backup_sqlite(output):
    parsed = make_url(database_url())
    if (
        parsed.get_backend_name() != "sqlite"
        or not parsed.database
        or parsed.database == ":memory:"
    ):
        raise ValueError(
            "Use pg_dump for PostgreSQL; this command backs up file-based SQLite"
        )
    source = Path(parsed.database).resolve()
    destination = Path(output).resolve()
    if not source.is_file():
        raise ValueError("Source database does not exist")
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    try:
        with (
            closing(
                sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
            ) as original,
            closing(sqlite3.connect(destination)) as copied,
        ):
            original.backup(copied)
            if copied.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Backup integrity check failed")
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def import_sqlite(source_path, target_url):
    source_path = Path(source_path).resolve()
    if not source_path.is_file():
        raise ValueError("Source database does not exist")
    if make_url(target_url).get_backend_name() != "postgresql":
        raise ValueError("Target must be PostgreSQL")
    source = build_engine("sqlite:///" + source_path.as_posix())
    target = build_engine(target_url)
    try:
        verify_database(source)
        verify_database(target)
        tables = Base.metadata.sorted_tables
        total = 0
        with source.connect() as original, target.begin() as destination:
            original.exec_driver_sql(
                "BEGIN"
            )  # Consistent SQLite snapshot across all tables.
            names = ", ".join(
                destination.dialect.identifier_preparer.quote(table.name)
                for table in tables
            )
            destination.exec_driver_sql(
                "LOCK TABLE " + names + " IN ACCESS EXCLUSIVE MODE"
            )
            if any(
                destination.scalar(select(func.count()).select_from(table))
                for table in tables
            ):
                raise ValueError("Target is not empty; migration refused")
            sequences = dict(
                original.exec_driver_sql("SELECT name, seq FROM sqlite_sequence").all()
            )
            for table in tables:
                rows = original.execute(select(table)).mappings()
                while batch := rows.fetchmany(100):
                    destination.execute(table.insert(), [dict(row) for row in batch])
                    total += len(batch)
                if "id" in table.c:
                    maximum = max(
                        destination.scalar(select(func.max(table.c.id))) or 0,
                        sequences.get(table.name, 0),
                    )
                    destination.execute(
                        text(
                            "SELECT setval(pg_get_serial_sequence(:table_name, 'id'), :value, :called)"
                        ),
                        {
                            "table_name": table.name,
                            "value": maximum or 1,
                            "called": maximum > 0,
                        },
                    )
            original.rollback()
        return total
    finally:
        source.dispose()
        target.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    backup = commands.add_parser("backup-sqlite")
    backup.add_argument("--output", required=True)
    migration = commands.add_parser("import-sqlite")
    migration.add_argument("--source", required=True)
    migration.add_argument("--confirm-empty-target", action="store_true", required=True)
    args = parser.parse_args()
    try:
        if args.command == "backup-sqlite":
            backup_sqlite(args.output)
            print(
                "Backup created and integrity checked; protect the backup as private data."
            )
        else:
            total = import_sqlite(args.source, database_url())
            print(f"Migration committed: {total} rows copied. Source kept unchanged.")
    except Exception as error:
        # Driver exception strings can contain credentials or submitted values.
        parser.exit(
            1,
            f"Operation failed ({type(error).__name__}); source preserved. Check configuration and target state.\n",
        )


if __name__ == "__main__":
    main()
