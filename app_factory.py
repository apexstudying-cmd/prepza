"""Flask application construction and shared extension initialization.

The legacy `app.py` module continues to export the configured global `app`
and `limiter` objects for WSGI, tests, migrations and existing integrations.
"""
import os
from datetime import timedelta

from flask import Flask
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from extensions import db, init_extensions


def create_app() -> tuple[Flask, Limiter]:
    """Create the Flask application with the existing runtime configuration."""
    app = Flask("app", static_folder="frontend/dist", static_url_path="")
    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=["200 per hour"],
        storage_uri=os.environ.get("REDIS_URL", "memory://"),
        storage_options={
            "socket_connect_timeout": 2,
            "socket_timeout": 2,
        } if os.environ.get("REDIS_URL") else {},
    )
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    init_extensions(app)
    return app, limiter
