"""Session, administrator and CSRF authorization guards."""
from functools import wraps
import hmac

from flask import jsonify, request, session

from extensions import db
from user_models import User


def _admin_authorization_failure():
    """Return a server-side denial response for the privileged admin surface."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    user = db.session.get(User, user_id)
    if not user or not user.is_admin or user.is_suspended:
        return jsonify({"error": "Forbidden"}), 403

    return None


def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        denied = _admin_authorization_failure()
        if denied:
            return denied
        return f(*args, **kwargs)
    return decorated


def _is_admin_surface(path: str) -> bool:
    return (
        path == "/admin"
        or path.startswith("/admin/")
        or path == "/api/admin"
        or path.startswith("/api/admin/")
    )


def login_required(f):
    """Require an authenticated Prepza session for protected routes."""
    @wraps(f)
    def decorated(*args, **kwargs):
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401
        return f(*args, **kwargs)
    return decorated


def require_csrf(f):
    """Require the session-bound CSRF token on mutating authenticated routes."""
    @wraps(f)
    def decorated(*args, **kwargs):
        provided = request.headers.get("X-CSRF-Token")
        expected = session.get("csrf_token")
        if not provided or not expected or not hmac.compare_digest(provided, expected):
            return jsonify({"error": "Missing or invalid CSRF token"}), 403
        return f(*args, **kwargs)
    return decorated
