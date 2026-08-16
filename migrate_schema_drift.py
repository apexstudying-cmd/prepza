"""
Fixes the drift diagnose_schema.py found:
  - adds university_id / program_id / requested_program_name to "user"
  - creates the missing organisation / organisation_member / opportunity /
    opportunity_promotion tables, using app.py's own model definitions
    (not hand-written SQL) so there's no risk of the migration drifting
    from the actual models.

Safe to re-run - every step checks before acting.

Usage:
    cd ~/desktop/prepza
    python migrate_schema_drift.py
"""
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise SystemExit("DATABASE_URL not found - make sure .env is present in this folder.")

import app as prepza_app  # noqa: E402 - imported after .env load, like app.py itself expects

USER_COLUMN_STATEMENTS = [
    'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS university_id INTEGER;',
    'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS program_id INTEGER;',
    'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS requested_program_name VARCHAR(150);',
    '''DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'user_university_id_fkey'
        ) THEN
            ALTER TABLE "user" ADD CONSTRAINT user_university_id_fkey
                FOREIGN KEY (university_id) REFERENCES university(id);
        END IF;
    END $$;''',
    '''DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'user_program_id_fkey'
        ) THEN
            ALTER TABLE "user" ADD CONSTRAINT user_program_id_fkey
                FOREIGN KEY (program_id) REFERENCES program(id);
        END IF;
    END $$;''',
]

MISSING_TABLE_NAMES = {"organisation", "organisation_member", "opportunity", "opportunity_promotion"}


def main():
    engine = create_engine(DATABASE_URL)

    print('Step 1: adding missing columns to "user"...')
    with engine.begin() as conn:
        for stmt in USER_COLUMN_STATEMENTS:
            print(f"  Running: {stmt.strip().splitlines()[0]}")
            conn.execute(text(stmt))

    print()
    print("Step 2: creating missing tables from app.py's model definitions...")
    tables_to_create = [
        t for name, t in prepza_app.db.metadata.tables.items() if name in MISSING_TABLE_NAMES
    ]
    found_names = {t.name for t in tables_to_create}
    not_found = MISSING_TABLE_NAMES - found_names
    if not_found:
        print(f"  WARNING: these expected tables aren't in app.py's models: {not_found}")

    prepza_app.db.metadata.create_all(bind=engine, tables=tables_to_create, checkfirst=True)
    for t in tables_to_create:
        print(f"  Created (or already existed): {t.name}")

    print()
    print("Done. Run diagnose_schema.py again to confirm zero drift remains.")


if __name__ == "__main__":
    main()
