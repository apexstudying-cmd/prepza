"""
Chunk 9 - Step 6b: add recipient_first_name/recipient_last_name columns
to the already-existing ambassador_payout table.

db.create_all() only creates whole missing tables - it never alters an
existing one, so this needs an explicit ALTER TABLE. Safe to re-run:
checks each column's existence first and skips it if already present.

Usage:
    python migrate_chunk9_payout_columns.py
"""
from sqlalchemy import inspect, text

from app import app, db

NEW_COLUMNS = {
    "recipient_first_name": 'ALTER TABLE ambassador_payout ADD COLUMN recipient_first_name VARCHAR(100) NOT NULL DEFAULT \'\'',
    "recipient_last_name": 'ALTER TABLE ambassador_payout ADD COLUMN recipient_last_name VARCHAR(100) NOT NULL DEFAULT \'\'',
}

with app.app_context():
    inspector = inspect(db.engine)
    existing_cols = {c["name"] for c in inspector.get_columns("ambassador_payout")}

    for col_name, ddl in NEW_COLUMNS.items():
        if col_name in existing_cols:
            print(f"SKIP: {col_name} already exists")
            continue
        print(f"Adding column: {col_name}")
        with db.engine.begin() as conn:
            conn.execute(text(ddl))
        print(f"OK: {col_name} added")

    # Drop the DEFAULT '' now that the column exists, so future ORM
    # inserts are required to supply a real value (matches the
    # nullable=False, no-default column definition in the model) -
    # the DEFAULT above only existed to satisfy any pre-existing rows
    # during the ALTER TABLE itself.
    with db.engine.begin() as conn:
        for col_name in NEW_COLUMNS:
            conn.execute(text(f"ALTER TABLE ambassador_payout ALTER COLUMN {col_name} DROP DEFAULT"))

    inspector = inspect(db.engine)
    final_cols = {c["name"] for c in inspector.get_columns("ambassador_payout")}
    missing = set(NEW_COLUMNS) - final_cols
    if missing:
        raise SystemExit(f"ABORT: still missing after migration: {sorted(missing)}")
    print("OK: both columns confirmed present on ambassador_payout.")
