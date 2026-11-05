"""Protect the shared Flask-SQLAlchemy extension initialization boundary."""

from pathlib import Path

from flask import Flask
from flask_sqlalchemy import SQLAlchemy

ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")
RUNTIME_SOURCE = (ROOT / "db_runtime.py").read_text(encoding="utf-8")


def test_application_keeps_legacy_app_db_exports_through_shared_extensions():
    assert "from extensions import db, init_extensions" in APP_SOURCE
    assert "init_extensions(app)" in APP_SOURCE
    assert "db = SQLAlchemy(app)" not in APP_SOURCE
    assert "from db_runtime import configure_sqlalchemy_runtime" not in APP_SOURCE


def test_runtime_configuration_does_not_patch_sqlalchemy_constructor():
    assert "SQLAlchemy.__init__ =" not in RUNTIME_SOURCE
    assert "_prepza_runtime_patched" not in RUNTIME_SOURCE
    assert "def configure_sqlalchemy_runtime(app):" in RUNTIME_SOURCE


def test_shared_extension_initializes_sqlite_app_and_preserves_session_lifecycle():
    from extensions import db, init_extensions

    app = Flask("prepza-extension-contract")
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite://",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        TESTING=True,
    )
    init_extensions(app)

    with app.app_context():
        assert db.engine.dialect.name == "sqlite"
        assert db.session is not None
        db.session.remove()


def test_postgresql_pool_configuration_is_applied_before_extension_init(monkeypatch):
    from extensions import init_extensions

    monkeypatch.setenv("DB_POOL_RECYCLE_SECONDS", "420")
    monkeypatch.setenv("DB_POOL_TIMEOUT_SECONDS", "17")
    monkeypatch.setenv("DB_POOL_SIZE", "4")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "6")

    app = Flask("prepza-postgres-config-contract")
    app.config["SQLALCHEMY_DATABASE_URI"] = "postgresql://user:pass@localhost/prepza"
    init_extensions(app)

    assert app.config["SQLALCHEMY_ENGINE_OPTIONS"] == {
        "pool_pre_ping": True,
        "pool_recycle": 420,
        "pool_timeout": 17,
        "pool_size": 4,
        "max_overflow": 6,
    }


def test_existing_explicit_engine_options_are_not_overwritten(monkeypatch):
    from extensions import init_extensions

    monkeypatch.setenv("DB_POOL_SIZE", "9")
    app = Flask("prepza-explicit-engine-options-contract")
    app.config["SQLALCHEMY_DATABASE_URI"] = "postgresql://user:pass@localhost/prepza"
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_size": 2,
        "pool_pre_ping": False,
        "pool_timeout": 31,
    }

    init_extensions(app)

    assert app.config["SQLALCHEMY_ENGINE_OPTIONS"] == {
        "pool_size": 2,
        "pool_pre_ping": False,
        "pool_timeout": 31,
        "pool_recycle": 300,
        "max_overflow": 5,
    }


def test_sqlite_and_missing_database_uri_skip_postgresql_pool_defaults():
    from db_runtime import configure_sqlalchemy_runtime

    for uri in ("sqlite://", None):
        app = Flask("prepza-sqlite-runtime-contract")
        app.config["SQLALCHEMY_DATABASE_URI"] = uri
        configure_sqlalchemy_runtime(app)
        assert "SQLALCHEMY_ENGINE_OPTIONS" not in app.config
