"""Disposable authenticated users for focused realtime/calling runtime tests."""
from __future__ import annotations

from contextlib import contextmanager
from uuid import uuid4

from werkzeug.security import generate_password_hash

from app import app, db, User


@contextmanager
def runtime_test_users():
    """Create three isolated users and remove them after the focused runtime test."""
    suffix = uuid4().hex
    emails = {
        "primary": f"runtime.primary.{suffix}@test.invalid",
        "peer": f"runtime.peer.{suffix}@test.invalid",
        "attacker": f"runtime.attacker.{suffix}@test.invalid",
    }

    with app.app_context():
        app.config.update(
            TESTING=True,
            SESSION_COOKIE_SECURE=False,
            PROPAGATE_EXCEPTIONS=True,
        )
        users = {}
        try:
            for role, email in emails.items():
                user = User(
                    email=email,
                    password_hash=generate_password_hash("Runtime!Test123"),
                    year=2,
                    semester=1,
                    display_name=f"Runtime {role}",
                    email_verified=True,
                    is_admin=False,
                    is_suspended=False,
                    profile_visibility="public",
                    who_can_message="everyone",
                    who_can_follow="everyone",
                    read_receipts_enabled=True,
                    university_id=None,
                    program_id=None,
                    session_version=0,
                )
                db.session.add(user)
                users[role] = user

            db.session.commit()
            db.session.expire_all()
            users = {role: db.session.get(User, user.id) for role, user in users.items()}
            yield users
        finally:
            user_ids = [user.id for user in users.values() if user is not None]
            for user_id in user_ids:
                db.session.execute(
                    db.text("DELETE FROM user_key WHERE user_id = :user_id"),
                    {"user_id": user_id},
                )
            for user in users.values():
                if user is not None:
                    db.session.delete(user)
            db.session.commit()
            db.session.remove()
