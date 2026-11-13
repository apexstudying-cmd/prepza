from __future__ import annotations

from datetime import timedelta

from flask import Flask

from app_factory import create_app
from extensions import db


def test_app_factory_preserves_legacy_flask_configuration_and_shared_database(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("SECRET_KEY", "factory-contract-secret")
    monkeypatch.delenv("REDIS_URL", raising=False)

    app, limiter = create_app()

    assert isinstance(app, Flask)
    assert app.name == "app"
    assert app.config["SQLALCHEMY_DATABASE_URI"] == "sqlite://"
    assert app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] is False
    assert app.config["SECRET_KEY"] == "factory-contract-secret"
    assert app.config["PERMANENT_SESSION_LIFETIME"] == timedelta(days=7)
    assert app.config["SESSION_COOKIE_SECURE"] is True
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"

    with app.app_context():
        assert db.engine.dialect.name == "sqlite"
        assert db.session is not None

    assert limiter is not None


def test_factory_keeps_limiter_default_and_memory_fallback(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.delenv("REDIS_URL", raising=False)

    app, limiter = create_app()

    registered = app.extensions.get("limiter")
    assert registered is limiter or (isinstance(registered, set) and limiter in registered)



def test_launch_wiring_audit_follows_the_extracted_factory_and_route_registry():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    audit = (root / "tools" / "verify_launch_wiring.py").read_text(encoding="utf-8")
    assert 'APP_FACTORY = ROOT / "app_factory.py"' in audit
    assert 'ROUTE_REGISTRY = ROOT / "route_registry.py"' in audit
    assert 'static_folder="frontend/dist"' in audit
    assert "register_foundation_routes(app, db)" in audit
    assert "register_usage_billing(app, db)" in audit
    assert "register_organisation_billing(app, db)" in audit
    assert "register_discovery(app, db)" in audit
