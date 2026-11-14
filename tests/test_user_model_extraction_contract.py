from __future__ import annotations

from pathlib import Path

from user_models import User

ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")


def test_user_model_is_domain_owned_and_kept_available_from_legacy_app() -> None:
    assert "from user_models import User" in APP_SOURCE
    assert "class User(db.Model)" not in APP_SOURCE
    assert User.__tablename__ == "user"
    expected = {
        "id", "email", "password_hash", "year", "semester", "display_name",
        "avatar_storage_path", "bio", "phone_number", "email_verified",
        "profile_visibility", "who_can_message", "who_can_follow",
        "read_receipts_enabled", "verification_token", "reset_token",
        "reset_token_expiry", "is_admin", "university_id", "program_id",
        "requested_program_name", "created_at", "signup_source", "is_suspended",
        "last_active_at", "session_version",
    }
    assert set(User.__table__.columns.keys()) == expected


def test_user_privacy_and_session_defaults_are_unchanged() -> None:
    assert User.__table__.c.profile_visibility.default.arg == "public"
    assert User.__table__.c.who_can_message.default.arg == "everyone"
    assert User.__table__.c.who_can_follow.default.arg == "everyone"
    assert User.__table__.c.read_receipts_enabled.default.arg is True
    assert User.__table__.c.session_version.default.arg == 0
    targets = {fk.target_fullname for fk in User.__table__.c.university_id.foreign_keys | User.__table__.c.program_id.foreign_keys}
    assert targets == {"university.id", "program.id"}
