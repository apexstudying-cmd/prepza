from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from flask import Flask

from social_follow_routes import register_social_follow_routes

ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")
REGISTRY_SOURCE = (ROOT / "route_registry.py").read_text(encoding="utf-8")
MODULE_SOURCE = (ROOT / "social_follow_routes.py").read_text(encoding="utf-8")


def test_app_delegates_follow_routes_without_changing_shared_notification_helpers() -> None:
    assert "register_social_follow_routes(" in APP_SOURCE
    assert "should_notify=lambda user_id, category: should_notify(user_id, category)" in APP_SOURCE
    assert "send_push_notification=lambda *args, **kwargs: send_push_notification(*args, **kwargs)" in APP_SOURCE
    assert "def should_notify(user_id, category):" in APP_SOURCE
    assert 'from social_follow_routes import register_social_follow_routes as register' in REGISTRY_SOURCE
    assert "def _serialize_follow_user(" not in APP_SOURCE
    assert "from app import" not in MODULE_SOURCE
    for route in (
        '@app.route("/users/<int:target_user_id>/follow", methods=["POST"])',
        '@app.route("/follow-requests")',
        '@app.route("/follow-requests/<int:request_id>/accept", methods=["POST"])',
        '@app.route("/follow-requests/<int:request_id>/decline", methods=["POST"])',
        '@app.route("/users/<int:target_user_id>/follow", methods=["DELETE"])',
        '@app.route("/users/<int:target_user_id>/followers")',
        '@app.route("/users/<int:target_user_id>/following")',
        '@app.route("/users/<int:target_user_id>/follow-summary")',
        '@app.route("/users/<int:target_user_id>/public-profile")',
    ):
        assert route not in APP_SOURCE
        assert route in MODULE_SOURCE


def test_follow_route_registration_and_private_profile_boundary() -> None:
    app = Flask("prepza-social-follow-contract")
    app.config.update(TESTING=True, SECRET_KEY="social-follow-contract-secret")

    class User:
        id = 23
        is_suspended = False
        profile_visibility = "private"
        display_name = "Private Student"
        email = "must-not-be-returned@example.invalid"

    class FakeSession:
        def get(self, model, user_id):
            return User() if model is User and user_id == 23 else None

    db = SimpleNamespace(session=FakeSession())
    identity = lambda function: function

    register_social_follow_routes(
        app,
        db,
        User=User,
        Follow=object(),
        FollowRequest=object(),
        Notification=object(),
        University=object(),
        Program=object(),
        Document=object(),
        XpEvent=object(),
        StudyTimeLog=object(),
        display_name=lambda user: user.display_name,
        get_signed_url=lambda *_args, **_kwargs: None,
        should_notify=lambda *_args: False,
        send_push_notification=lambda *_args, **_kwargs: None,
        require_csrf=identity,
    )

    routes = {}
    for rule in app.url_map.iter_rules():
        routes.setdefault(rule.rule, set()).update(rule.methods)

    assert "POST" in routes["/users/<int:target_user_id>/follow"]
    assert "DELETE" in routes["/users/<int:target_user_id>/follow"]
    assert "GET" in routes["/follow-requests"]
    assert "POST" in routes["/follow-requests/<int:request_id>/accept"]
    assert "POST" in routes["/follow-requests/<int:request_id>/decline"]
    assert "GET" in routes["/users/<int:target_user_id>/followers"]
    assert "GET" in routes["/users/<int:target_user_id>/following"]
    assert "GET" in routes["/users/<int:target_user_id>/follow-summary"]
    assert "GET" in routes["/users/<int:target_user_id>/public-profile"]
    assert MODULE_SOURCE.count("@require_csrf") == 4

    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 17
    response = client.get("/users/23/public-profile")
    assert response.status_code == 200
    assert response.get_json() == {
        "user_id": 23,
        "display_name": "Private Student",
        "is_private": True,
    }
    assert "email" not in response.get_json()
