"""
One-time seed script: ensures default rows exist in the SystemSetting table
for maintenance mode. Safe to run multiple times (idempotent - only inserts
rows that don't already exist, never overwrites existing values).

Requires a real .env with DATABASE_URL set (this hits your live Supabase DB).

Run from your project root:
    python seed_system_settings.py
"""

import os
from dotenv import load_dotenv

load_dotenv()

from app import app, db, SystemSetting  # noqa: E402

DEFAULTS = {
    "maintenance_mode": "false",
    "maintenance_message": "Prepza is temporarily down for maintenance. Please check back shortly.",
    "support_email": "",
    "support_phone": "",
    "support_message": "Need help? Contact the Prepza support team.",
}


def main():
    with app.app_context():
        created = []
        for key, default_value in DEFAULTS.items():
            existing = SystemSetting.query.filter_by(key=key).first()
            if existing:
                print(f"'{key}' already exists (value: {existing.value!r}) - skipping.")
                continue
            db.session.add(SystemSetting(key=key, value=default_value))
            created.append(key)
        if created:
            db.session.commit()
            print(f"Created default rows for: {', '.join(created)}")
        else:
            print("Nothing to do - all SystemSetting rows already exist.")


if __name__ == "__main__":
    main()
