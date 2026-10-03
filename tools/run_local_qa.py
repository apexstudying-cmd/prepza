"""Bootstrap a disposable Prepza QA database and run the real-world test suite."""

from __future__ import annotations

import os
import re
import subprocess
import sys

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


QA_DATABASE_NAME = os.environ.get("QA_DATABASE_NAME", "prepza_qa")

if not re.fullmatch(r"[A-Za-z0-9_]+", QA_DATABASE_NAME):
    raise SystemExit("QA_DATABASE_NAME must contain only letters, numbers, and underscores")


def main() -> int:
    source_raw = os.environ.get("DATABASE_URL")
    if not source_raw:
        raise SystemExit("DATABASE_URL is required")

    source_url = make_url(source_raw)
    source_database = source_url.database or ""
    if source_database == QA_DATABASE_NAME or source_database.endswith("_qa"):
        raise SystemExit(
            f"Refusing to bootstrap QA from database '{source_database}'"
        )

    qa_url = source_url.set(database=QA_DATABASE_NAME)

    # The Docker PostgreSQL role used by Prepza is the local database owner.
    # Connect to the maintenance database only for CREATE DATABASE.
    maintenance_url = source_url.set(database="postgres")
    maintenance_engine = create_engine(
        maintenance_url,
        future=True,
        isolation_level="AUTOCOMMIT",
    )

    try:
        with maintenance_engine.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": QA_DATABASE_NAME},
            ).scalar()

            if not exists:
                owner = source_url.username
                if not owner:
                    raise SystemExit("DATABASE_URL does not contain a database user")
                owner_sql = '"' + owner.replace('"', '""') + '"'
                db_sql = '"' + QA_DATABASE_NAME.replace('"', '""') + '"'
                connection.exec_driver_sql(
                    f"CREATE DATABASE {db_sql} OWNER {owner_sql}"
                )
                print(f"Created disposable database: {QA_DATABASE_NAME}")
            else:
                print(f"Using existing disposable database: {QA_DATABASE_NAME}")
    finally:
        maintenance_engine.dispose()

    os.environ["DATABASE_URL"] = qa_url.render_as_string(hide_password=False)

    print("Applying Alembic migrations to QA database...")
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    print("Alembic upgrade head: OK")

    print("Running real-world QA suite...")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests/test_local_qa_real_world.py"],
        env=os.environ.copy(),
        check=False,
    )

    print(f"QA database retained for inspection: {qa_url.render_as_string(hide_password=True)}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
