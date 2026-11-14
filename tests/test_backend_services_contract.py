from __future__ import annotations

import json
import sys
from types import ModuleType

from audit_service import log_admin_action
from app_factory import create_app
from extensions import db
from push_notifications import send_push_notification
from academic_models import University, Program
from security_models import AuditLog, PushSubscription
from user_models import User


def _app_with_account_tables(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("SECRET_KEY", "service-contract-secret")
    monkeypatch.delenv("REDIS_URL", raising=False)
    app, _limiter = create_app()
    tables = [University.__table__, Program.__table__, User.__table__, AuditLog.__table__, PushSubscription.__table__]
    with app.app_context():
        db.metadata.create_all(bind=db.engine, tables=tables)
        user = User(email="service@example.test", password_hash="x")
        db.session.add(user)
        db.session.commit()
        user_id = user.id
    return app, user_id, tables


def _cleanup(app, tables):
    with app.app_context():
        db.session.remove()
        db.metadata.drop_all(bind=db.engine, tables=list(reversed(tables)))


def test_audit_service_stages_serializable_details_without_committing(monkeypatch) -> None:
    app, user_id, tables = _app_with_account_tables(monkeypatch)
    try:
        with app.app_context():
            log_admin_action(user_id, "user.updated", "user", user_id, {"changed": ["bio"]})
            staged = next(row for row in db.session.new if isinstance(row, AuditLog))
            assert staged.details == json.dumps({"changed": ["bio"]})
            db.session.rollback()
            assert AuditLog.query.count() == 0
    finally:
        _cleanup(app, tables)


def test_audit_service_falls_back_to_string_for_non_json_details(monkeypatch) -> None:
    app, user_id, tables = _app_with_account_tables(monkeypatch)

    class OpaqueDetails:
        def __str__(self):
            return "opaque-audit-details"

    try:
        with app.app_context():
            log_admin_action(user_id, "user.updated", "user", user_id, OpaqueDetails())
            staged = next(row for row in db.session.new if isinstance(row, AuditLog))
            assert staged.details == "opaque-audit-details"
            db.session.rollback()
    finally:
        _cleanup(app, tables)


def test_push_service_skips_safely_when_vapid_credentials_are_missing(monkeypatch) -> None:
    app, user_id, tables = _app_with_account_tables(monkeypatch)
    monkeypatch.delenv("VAPID_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("VAPID_CLAIMS_EMAIL", raising=False)
    try:
        with app.app_context():
            assert send_push_notification(user_id, "title", "body") is None
    finally:
        _cleanup(app, tables)


def test_push_service_prunes_only_gone_subscriptions(monkeypatch) -> None:
    app, user_id, tables = _app_with_account_tables(monkeypatch)
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "test-private-key")
    monkeypatch.setenv("VAPID_CLAIMS_EMAIL", "mailto:test@example.test")

    class FakeResponse:
        status_code = 410

    class GoneError(Exception):
        response = FakeResponse()

    fake_module = ModuleType("pywebpush")
    fake_module.webpush = lambda **kwargs: (_ for _ in ()).throw(GoneError("gone"))
    fake_module.WebPushException = GoneError
    monkeypatch.setitem(sys.modules, "pywebpush", fake_module)

    try:
        with app.app_context():
            db.session.add(PushSubscription(
                user_id=user_id,
                endpoint="https://push.example.test/gone",
                p256dh_key="p256dh",
                auth_key="auth",
            ))
            db.session.commit()
            send_push_notification(user_id, "title", "body")
            assert PushSubscription.query.filter_by(user_id=user_id).count() == 0
    finally:
        _cleanup(app, tables)
