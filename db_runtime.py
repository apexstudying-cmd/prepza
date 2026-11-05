"""Database engine configuration applied before Flask-SQLAlchemy binds an app."""

import os


def configure_sqlalchemy_runtime(app):
    """Apply the existing PostgreSQL pool defaults without changing SQLite behavior."""
    uri = (app.config.get("SQLALCHEMY_DATABASE_URI") or "").lower()
    if not uri or uri.startswith("sqlite"):
        return

    options = app.config.setdefault("SQLALCHEMY_ENGINE_OPTIONS", {})
    options.setdefault("pool_pre_ping", True)
    options.setdefault("pool_recycle", int(os.environ.get("DB_POOL_RECYCLE_SECONDS", "300")))
    options.setdefault("pool_timeout", int(os.environ.get("DB_POOL_TIMEOUT_SECONDS", "20")))
    options.setdefault("pool_size", int(os.environ.get("DB_POOL_SIZE", "5")))
    options.setdefault("max_overflow", int(os.environ.get("DB_MAX_OVERFLOW", "5")))
