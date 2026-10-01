"""Initialize the SQLite schema for CI runtime regression tests.

This is test-only setup: production migrations remain the source of truth.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import app, db

with app.app_context():
    db.create_all()
    print("CI SQLite schema initialized.")
