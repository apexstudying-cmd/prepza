"""Shared Flask extensions with explicit initialization order.

The global `db` object is imported by legacy route modules, model declarations,
Alembic, and QA scripts. Keep that import surface stable while centralizing
extension construction and configuration.
"""

from flask_sqlalchemy import SQLAlchemy

from db_runtime import configure_sqlalchemy_runtime


db = SQLAlchemy()


def init_extensions(app):
    """Configure runtime options before binding the shared SQLAlchemy extension."""
    configure_sqlalchemy_runtime(app)
    db.init_app(app)
    return db
