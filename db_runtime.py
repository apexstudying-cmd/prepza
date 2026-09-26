import os
from sqlalchemy import event

def configure_sqlalchemy_runtime(app):
    uri=(app.config.get("SQLALCHEMY_DATABASE_URI") or "").lower()
    if not uri or uri.startswith("sqlite"):
        return
    # Keep stale Render/Supabase connections from surviving network idleness.
    app.config.setdefault("SQLALCHEMY_ENGINE_OPTIONS", {})
    opts=app.config["SQLALCHEMY_ENGINE_OPTIONS"]
    opts.setdefault("pool_pre_ping", True)
    opts.setdefault("pool_recycle", int(os.environ.get("DB_POOL_RECYCLE_SECONDS","300")))
    opts.setdefault("pool_timeout", int(os.environ.get("DB_POOL_TIMEOUT_SECONDS","20")))
    opts.setdefault("pool_size", int(os.environ.get("DB_POOL_SIZE","5")))
    opts.setdefault("max_overflow", int(os.environ.get("DB_MAX_OVERFLOW","5")))
