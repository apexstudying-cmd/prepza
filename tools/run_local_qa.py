"""Bootstrap a disposable Prepza QA database and run the full QA suite."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

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

    # These two additive tables are managed by the repository's SQL migration
    # ledger rather than Alembic. Apply them to the disposable QA database too,
    # otherwise the app's retrieval/observability contracts would be tested
    # against a schema different from the browser app's database.
    migration_dir = Path(__file__).resolve().parents[1] / "migrations"
    additive_migrations = [
        migration_dir / "20261029_document_page_text.sql",
        migration_dir / "20261029_request_observability.sql",
    ]
    qa_engine = create_engine(qa_url, future=True)
    try:
        with qa_engine.begin() as connection:
            for migration_path in additive_migrations:
                connection.exec_driver_sql(migration_path.read_text(encoding="utf-8"))
                print(f"Applied QA SQL migration: {migration_path.name}")
            page_table, event_table = connection.exec_driver_sql(
                "SELECT to_regclass('public.document_page_text'), "
                "to_regclass('public.request_observability_event')"
            ).one()
            if not page_table or not event_table:
                raise RuntimeError("Required retrieval/observability QA tables are missing")
    finally:
        qa_engine.dispose()

    print("Running full real-world and route semantic QA suite...")
    test_files = [
        "tests/test_local_qa_real_world.py",
        "tests/test_route_security_matrix.py",
        "tests/test_authenticated_route_matrix.py",
        "tests/test_local_qa_authz.py",
        "tests/test_frontend_ai_generation_contract.py",
        "tests/test_ai_artifact_fingerprint.py",
        "tests/test_ai_generation_store.py",
        "tests/test_ai_economics.py",
        "tests/test_ai_reusable_generation.py",
        "tests/test_realtime_e2ee_runtime.py",
        "scripts/test_personal_streak_runtime.py",
    ]
    # Keep QA rate-limit counters separate from the running app's Redis DB.
    # This preserves the real rate-limit rules while preventing earlier local
    # QA runs from consuming the disposable suite's request budget.
    qa_env = os.environ.copy()
    qa_env["PREPZA_FULL_QA"] = "1"
    qa_env["REDIS_URL"] = "memory://"

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *test_files],
        env=qa_env,
        check=False,
    )

    print(f"QA database retained for inspection: {qa_url.render_as_string(hide_password=True)}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
