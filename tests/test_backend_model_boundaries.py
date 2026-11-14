from __future__ import annotations

from pathlib import Path

from observability_models import RequestObservabilityEvent
from security_models import AuditLog, PushSubscription, UserKey

ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")


def test_observability_model_is_owned_by_its_domain_module() -> None:
    assert "from observability_models import RequestObservabilityEvent" in APP_SOURCE
    assert "class RequestObservabilityEvent" not in APP_SOURCE
    assert RequestObservabilityEvent.__tablename__ == "request_observability_event"
    columns = set(RequestObservabilityEvent.__table__.columns.keys())
    assert columns == {"id", "request_id", "method", "route", "status_code", "duration_ms", "occurred_at"}
    assert "body" not in columns
    assert "user_id" not in columns


def test_security_and_audit_models_keep_existing_table_and_column_contracts() -> None:
    assert "from security_models import AuditLog, PushSubscription, UserKey" in APP_SOURCE
    for model, table, columns in (
        (AuditLog, "audit_log", {"id", "actor_id", "action", "target_type", "target_id", "details", "created_at"}),
        (PushSubscription, "push_subscription", {"id", "user_id", "endpoint", "p256dh_key", "auth_key", "created_at"}),
        (UserKey, "user_key", {"id", "user_id", "public_key", "encrypted_private_key", "kdf_salt", "created_at", "updated_at"}),
    ):
        assert model.__tablename__ == table
        assert set(model.__table__.columns.keys()) == columns


def test_security_model_foreign_keys_and_unique_constraints_are_preserved() -> None:
    assert next(iter(AuditLog.__table__.c.actor_id.foreign_keys)).target_fullname == "user.id"
    assert next(iter(PushSubscription.__table__.c.user_id.foreign_keys)).target_fullname == "user.id"
    assert next(iter(UserKey.__table__.c.user_id.foreign_keys)).target_fullname == "user.id"
    assert PushSubscription.__table__.c.endpoint.unique is True
    assert UserKey.__table__.c.user_id.unique is True
