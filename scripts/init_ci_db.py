"""Initialize the minimal SQLite schema needed by CI runtime regressions.

This is test-only setup: production migrations remain the source of truth.
The runtime socket/call tests require the User table for authenticated-session
checks. Creating the entire application metadata would also pull in optional
models whose foreign-key targets are not imported by these focused tests.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import app, db

with app.app_context():
    user_table = db.metadata.tables.get("user")
    if user_table is None:
        raise RuntimeError("CI schema setup: user table is not registered")
    user_table.create(bind=db.engine, checkfirst=True)
    print("CI SQLite User schema initialized.")
