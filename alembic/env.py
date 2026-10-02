"""Alembic environment for Prepza."""
from __future__ import annotations
import os, sys
from pathlib import Path
from alembic import context
from sqlalchemy import create_engine, inspect
from dotenv import load_dotenv
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")
config = context.config
database_url = os.environ.get("DATABASE_URL")
if not database_url:
    raise RuntimeError("DATABASE_URL is required for Alembic")
target_metadata = None
def _database_has_schema() -> bool:
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            return inspect(connection).has_table("user", schema="public")
    finally:
        engine.dispose()
if _database_has_schema():
    from app import db
    target_metadata = db.metadata
def include_object(object_, name, type_, reflected, compare_to):
    if type_ == "table" and reflected and compare_to is None:
        return False
    return True
def run_migrations_offline():
    context.configure(url=database_url,target_metadata=target_metadata,literal_binds=True,dialect_opts={"paramstyle":"named"},compare_type=True,include_object=include_object)
    with context.begin_transaction():
        context.run_migrations()
def run_migrations_online():
    connectable = create_engine(database_url)
    try:
        with connectable.connect() as connection:
            context.configure(connection=connection,target_metadata=target_metadata,compare_type=True,include_object=include_object)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
