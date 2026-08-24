"""
Chunk 9 - Step 2: create the ambassador, referral, ambassador_payout
tables.

Run locally from the repo root, with your .env DATABASE_URL set (same
as always - app.py's own load_dotenv() picks it up when we import it
below). Safe to re-run: db.create_all() only creates tables that don't
already exist yet - it never alters or drops anything, so running this
twice (or after future chunks add more tables) is a no-op for tables
already present.

Usage:
    python migrate_chunk9_tables.py
"""
from sqlalchemy import inspect

from app import app, db, Ambassador, Referral, AmbassadorPayout

EXPECTED_TABLES = {"ambassador", "referral", "ambassador_payout"}

with app.app_context():
    inspector = inspect(db.engine)
    before = set(inspector.get_table_names())
    missing_before = EXPECTED_TABLES - before

    if not missing_before:
        print("OK: all three tables already exist - nothing to do.")
    else:
        print(f"Creating: {sorted(missing_before)}")
        db.create_all()

        inspector = inspect(db.engine)
        after = set(inspector.get_table_names())
        still_missing = EXPECTED_TABLES - after
        if still_missing:
            raise SystemExit(f"ABORT: still missing after create_all(): {sorted(still_missing)}")
        print(f"OK: created {sorted(missing_before)}")

    # Quick sanity check on columns, so a mismatch between the model
    # and an already-existing table (e.g. from a partial prior run)
    # surfaces now rather than at the first real request.
    inspector = inspect(db.engine)
    for table_name, model in (
        ("ambassador", Ambassador),
        ("referral", Referral),
        ("ambassador_payout", AmbassadorPayout),
    ):
        actual_cols = {c["name"] for c in inspector.get_columns(table_name)}
        expected_cols = {c.name for c in model.__table__.columns}
        missing = expected_cols - actual_cols
        if missing:
            raise SystemExit(f"ABORT: {table_name} is missing columns {sorted(missing)} - schema drift?")
    print("OK: column check passed for all three tables.")
