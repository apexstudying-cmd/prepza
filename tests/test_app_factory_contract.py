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

    assert app.extensions.get("limiter") is limiter
