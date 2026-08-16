"""
Chunk 8 DB migration - adds the new Pesapal/subscription columns to the
payment table and relaxes phone_number to nullable. Safe to re-run (every
statement is idempotent).

Run this AFTER both patch_chunk8_pesapal.py and patch_chunk8_pesapal_part2.py
have been applied, so the SQLAlchemy model matches the DB.

Usage:
    cd ~/desktop/prepza
    python migrate_chunk8_pesapal.py
"""
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise SystemExit("DATABASE_URL not found - make sure .env is present in this folder.")

STATEMENTS = [
    'ALTER TABLE payment ALTER COLUMN phone_number DROP NOT NULL;',
    "ALTER TABLE payment ADD COLUMN IF NOT EXISTS provider VARCHAR(20) NOT NULL DEFAULT 'pesapal';",
    'ALTER TABLE payment ADD COLUMN IF NOT EXISTS merchant_reference VARCHAR(50);',
    'ALTER TABLE payment ADD COLUMN IF NOT EXISTS order_tracking_id VARCHAR(100);',
    "ALTER TABLE payment ADD COLUMN IF NOT EXISTS payment_type VARCHAR(20) NOT NULL DEFAULT 'content';",
    'ALTER TABLE payment ADD COLUMN IF NOT EXISTS plan VARCHAR(20);',
    'ALTER TABLE payment ADD COLUMN IF NOT EXISTS subscription_expires_at TIMESTAMP;',
    '''DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'payment_merchant_reference_key'
        ) THEN
            ALTER TABLE payment ADD CONSTRAINT payment_merchant_reference_key UNIQUE (merchant_reference);
        END IF;
    END $$;''',
    '''DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'payment_order_tracking_id_key'
        ) THEN
            ALTER TABLE payment ADD CONSTRAINT payment_order_tracking_id_key UNIQUE (order_tracking_id);
        END IF;
    END $$;''',
]


def main():
    engine = create_engine(DATABASE_URL)
    with engine.begin() as conn:
        for stmt in STATEMENTS:
            print(f"Running: {stmt.strip().splitlines()[0]}...")
            conn.execute(text(stmt))
    print()
    print("Migration complete.")


if __name__ == "__main__":
    main()
