"""Initialize the minimal SQLite schema needed by CI runtime regressions.

This is test-only setup: production migrations remain the source of truth.
The focused realtime/E2EE tests intentionally create only the tables they need.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import app, db, User

with app.app_context():
    user_table = db.metadata.tables.get("user")
    if user_table is None:
        raise RuntimeError("CI schema setup: user table is not registered")
    user_table.create(bind=db.engine, checkfirst=True)

    # E2EE identity runtime tests use the canonical user_key contract.
    # CI does not run the full production migration chain, so create only this
    # small table here instead of manufacturing the whole schema.
    db.session.execute(db.text("""
        CREATE TABLE IF NOT EXISTS user_key (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            public_key TEXT NOT NULL,
            encrypted_private_key TEXT,
            kdf_salt VARCHAR(64),
            created_at DATETIME,
            updated_at DATETIME,
            FOREIGN KEY(user_id) REFERENCES "user"(id) ON DELETE CASCADE
        )
    """))

    for user_id in (7, 8, 9):
        user = db.session.get(User, user_id)
        if user is None:
            db.session.add(User(
                id=user_id,
                email=f"ci-user-{user_id}@example.invalid",
                password_hash="ci-test-password",
                year=1,
                semester=1,
                session_version=1,
                is_suspended=False,
            ))
    db.session.commit()
    print("CI SQLite User + E2EE identity schema initialized.")
