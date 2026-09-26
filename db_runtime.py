import os
from flask_sqlalchemy import SQLAlchemy

def configure_sqlalchemy_runtime(app):
    uri=(app.config.get("SQLALCHEMY_DATABASE_URI") or "").lower()
    if not uri or uri.startswith("sqlite"):
        return
    opts=app.config.setdefault("SQLALCHEMY_ENGINE_OPTIONS", {})
    opts.setdefault("pool_pre_ping", True)
    opts.setdefault("pool_recycle", int(os.environ.get("DB_POOL_RECYCLE_SECONDS","300")))
    opts.setdefault("pool_timeout", int(os.environ.get("DB_POOL_TIMEOUT_SECONDS","20")))
    opts.setdefault("pool_size", int(os.environ.get("DB_POOL_SIZE","5")))
    opts.setdefault("max_overflow", int(os.environ.get("DB_MAX_OVERFLOW","5")))

# app.py creates its SQLAlchemy extension immediately after importing this
# module. Patch the constructor once so the connection settings are applied
# before Flask-SQLAlchemy creates its engine, without requiring a second
# initialization path or touching the model layer.
_original_init = SQLAlchemy.__init__
if not getattr(SQLAlchemy, "_prepza_runtime_patched", False):
    def _prepza_init(self, app=None, *args, **kwargs):
        if app is not None:
            configure_sqlalchemy_runtime(app)
        return _original_init(self, app, *args, **kwargs)
    SQLAlchemy.__init__ = _prepza_init
    SQLAlchemy._prepza_runtime_patched = True
