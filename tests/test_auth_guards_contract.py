from __future__ import annotations

from flask import Flask, session

from auth_guards import login_required, require_admin, require_csrf
from app_factory import create_app
from extensions import db
from user_models import User
from academic_models import University, Program


def _new_app(monkeypatch) -> Flask:
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("SECRET_KEY", "auth-guard-contract")
    monkeypatch.delenv("REDIS_URL", raising=False)
    app, _limiter = create_app()
    return app


def test_login_required_and_csrf_guards_fail_closed_and_allow_valid_session(monkeypatch) -> None:
    app = _new_app(monkeypatch)
    protected = login_required(lambda: ("ok", 200))
    csrf_protected = require_csrf(lambda: ("ok", 200))

    with app.test_request_context("/protected"):
        assert protected()[1] == 401
        session["user_id"] = 17
        assert protected() == ("ok", 200)
        assert csrf_protected()[1] == 403

    with app.test_request_context("/protected", headers={"X-CSRF-Token": "valid"}):
        session["csrf_token"] = "valid"
        assert csrf_protected() == ("ok", 200)


def test_admin_guard_checks_persisted_role_and_suspension_state(monkeypatch) -> None:
    app = _new_app(monkeypatch)
    with app.app_context():
        db.metadata.create_all(bind=db.engine, tables=[University.__table__, Program.__table__, User.__table__])
        ordinary = User(email="ordinary@example.test", password_hash="x", is_admin=False)
        admin = User(email="admin@example.test", password_hash="x", is_admin=True)
        suspended = User(email="suspended@example.test", password_hash="x", is_admin=True, is_suspended=True)
        db.session.add_all([ordinary, admin, suspended])
        db.session.commit()
        ordinary_id, admin_id, suspended_id = ordinary.id, admin.id, suspended.id

    protected = require_admin(lambda: ("ok", 200))
    with app.test_request_context("/admin"):
        assert protected()[1] == 401
        session["user_id"] = ordinary_id
        assert protected()[1] == 403
        session["user_id"] = suspended_id
        assert protected()[1] == 403
        session["user_id"] = admin_id
        assert protected() == ("ok", 200)

    with app.app_context():
        db.metadata.drop_all(bind=db.engine, tables=[User.__table__, Program.__table__, University.__table__])
