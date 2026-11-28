from __future__ import annotations

import json
from datetime import datetime, timedelta

from flask import Flask

from academic_models import Program, University
from app_factory import create_app
from auth_guards import require_admin
from extensions import db
from security_models import AuditLog
from user_models import User
from admin_audit_routes import register_admin_audit_routes


def _build_audit_app(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("SECRET_KEY", "admin-audit-contract-only")
    monkeypatch.delenv("REDIS_URL", raising=False)
    app, _limiter = create_app()
    app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
    tables = [University.__table__, Program.__table__, User.__table__, AuditLog.__table__]
    with app.app_context():
        db.metadata.create_all(bind=db.engine, tables=tables)
        admin = User(email="audit-admin@example.test", password_hash="x", is_admin=True)
        ordinary = User(email="audit-user@example.test", password_hash="x", is_admin=False)
        suspended = User(email="audit-suspended@example.test", password_hash="x", is_admin=True, is_suspended=True)
        db.session.add_all([admin, ordinary, suspended])
        db.session.commit()
        ids = {"admin": admin.id, "ordinary": ordinary.id, "suspended": suspended.id}
    register_admin_audit_routes(app, db, AuditLog, User, require_admin)
    return app, ids, tables


def _cleanup(app, tables):
    with app.app_context():
        db.session.remove()
        db.metadata.drop_all(bind=db.engine, tables=list(reversed(tables)))


def _authenticate(client, user_id):
    with client.session_transaction() as stored:
        stored["user_id"] = user_id


def test_admin_audit_route_keeps_path_method_and_persisted_admin_guard(monkeypatch):
    app, ids, tables = _build_audit_app(monkeypatch)
    try:
        routes = {
            rule.endpoint: (rule.rule, frozenset(rule.methods - {"HEAD", "OPTIONS"}))
            for rule in app.url_map.iter_rules()
            if rule.endpoint != "static"
        }
        assert routes == {
            "admin_list_audit_logs": ("/admin/audit-logs", frozenset({"GET"}))
        }

        client = app.test_client()
        anonymous = client.get("/admin/audit-logs")
        assert anonymous.status_code == 401
        assert anonymous.get_json() == {"error": "Not logged in"}

        _authenticate(client, ids["ordinary"])
        ordinary = client.get("/admin/audit-logs")
        assert ordinary.status_code == 403
        assert ordinary.get_json() == {"error": "Forbidden"}

        _authenticate(client, ids["suspended"])
        suspended = client.get("/admin/audit-logs")
        assert suspended.status_code == 403
        assert suspended.get_json() == {"error": "Forbidden"}

        _authenticate(client, ids["admin"])
        allowed = client.get("/admin/audit-logs")
        assert allowed.status_code == 200
        assert allowed.get_json() == {"page": 1, "logs": []}
    finally:
        _cleanup(app, tables)


def test_admin_audit_route_preserves_filters_order_pagination_and_detail_parsing(monkeypatch):
    app, ids, tables = _build_audit_app(monkeypatch)
    try:
        now = datetime.utcnow()
        entries = [
            AuditLog(
                actor_id=ids["admin"],
                action="user.updated",
                target_type="user",
                target_id=index,
                details=json.dumps({"index": index}) if index == 0 else ("not-json" if index == 1 else None),
                created_at=now - timedelta(minutes=index),
            )
            for index in range(51)
        ]
        old_entry = AuditLog(
            actor_id=ids["admin"], action="user.updated", target_type="user",
            target_id=999, details=None, created_at=now - timedelta(days=400),
        )
        other_entry = AuditLog(
            actor_id=ids["ordinary"], action="document.updated", target_type="document",
            target_id=1000, details=json.dumps({"source": "test"}), created_at=now - timedelta(hours=2),
        )
        with app.app_context():
            db.session.add_all([*entries, old_entry, other_entry])
            db.session.commit()
            expected_ids = [entry.id for entry in entries]
            other_id = other_entry.id

        client = app.test_client()
        _authenticate(client, ids["admin"])
        first_page = client.get("/admin/audit-logs?days=9999&page=1")
        assert first_page.status_code == 200
        payload = first_page.get_json()
        assert payload["page"] == 1
        assert len(payload["logs"]) == 50
        assert [row["id"] for row in payload["logs"]] == expected_ids[:50]
        assert payload["logs"][0]["actor_email"] == "audit-admin@example.test"
        assert payload["logs"][0]["details"] == {"index": 0}
        assert payload["logs"][1]["details"] == "not-json"
        assert payload["logs"][0]["created_at"] == entries[0].created_at.isoformat()

        second_page = client.get("/admin/audit-logs?days=9999&page=2")
        assert second_page.status_code == 200
        second_payload = second_page.get_json()
        assert second_payload["page"] == 2
        assert [row["id"] for row in second_payload["logs"]] == [expected_ids[50], other_id]
        assert second_payload["logs"][0] == {
            "id": expected_ids[50],
            "actor_id": ids["admin"],
            "actor_email": "audit-admin@example.test",
            "action": "user.updated",
            "target_type": "user",
            "target_id": 50,
            "details": None,
            "created_at": entries[50].created_at.isoformat(),
        }
        assert second_payload["logs"][1]["created_at"] == other_entry.created_at.isoformat()

        filtered = client.get(
            f"/admin/audit-logs?actor_id={ids['ordinary']}&action=UPDATED&target_type=document&page=0"
        )
        assert filtered.status_code == 200
        assert filtered.get_json()["page"] == 1
        assert filtered.get_json()["logs"] == [{
            "id": other_id,
            "actor_id": ids["ordinary"],
            "actor_email": "audit-user@example.test",
            "action": "document.updated",
            "target_type": "document",
            "target_id": 1000,
            "details": {"source": "test"},
            "created_at": other_entry.created_at.isoformat(),
        }]

        invalid_query = client.get("/admin/audit-logs?days=invalid&page=invalid")
        assert invalid_query.status_code == 200
        assert invalid_query.get_json()["page"] == 1
        assert len(invalid_query.get_json()["logs"]) == 50
    finally:
        _cleanup(app, tables)
