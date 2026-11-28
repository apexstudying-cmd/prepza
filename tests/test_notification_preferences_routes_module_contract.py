from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from flask import Flask

from notification_routes import register_notification_preference_routes

ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")
REGISTRY_SOURCE = (ROOT / "route_registry.py").read_text(encoding="utf-8")
MODULE_SOURCE = (ROOT / "notification_routes.py").read_text(encoding="utf-8")


def test_app_delegates_preference_and_push_routes_but_keeps_shared_helpers() -> None:
    assert "register_notification_preference_routes(" in APP_SOURCE
    assert "get_or_create_notification_prefs," in APP_SOURCE
    assert "def get_or_create_notification_prefs(user_id):" in APP_SOURCE
    assert "def should_notify(user_id, category):" in APP_SOURCE
    assert 'from notification_routes import register_notification_preference_routes as register' in REGISTRY_SOURCE
    for route in (
        '@app.route("/notification-preferences")',
        '@app.route("/notification-preferences", methods=["PATCH"])',
        '@app.route("/push/vapid-public-key")',
        '@app.route("/push/subscribe", methods=["POST"])',
        '@app.route("/push/subscribe", methods=["DELETE"])',
    ):
        assert route not in APP_SOURCE
        assert route in MODULE_SOURCE


def test_preference_and_push_routes_keep_methods_csrf_and_helper_behavior() -> None:
    app = Flask("prepza-notification-preferences-contract")
    app.config.update(TESTING=True, SECRET_KEY="notification-contract-test-secret")
    prefs = SimpleNamespace(community_enabled=True, messages_enabled=False)

    class FakeSession:
        commits = 0
        def commit(self):
            self.commits += 1

    db = SimpleNamespace(session=FakeSession())
    calls = []

    def get_prefs(user_id):
        calls.append(user_id)
        return prefs

    def identity(function):
        return function

    register_notification_preference_routes(
        app, db, object(), identity, get_prefs
    )

    routes = {}
    for rule in app.url_map.iter_rules():
        routes.setdefault(rule.rule, set()).update(rule.methods)
    assert "GET" in routes["/notification-preferences"]
    assert "PATCH" in routes["/notification-preferences"]
    assert "GET" in routes["/push/vapid-public-key"]
    assert "POST" in routes["/push/subscribe"]
    assert "DELETE" in routes["/push/subscribe"]

    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 17

    response = client.get("/notification-preferences")
    assert response.status_code == 200
    assert response.get_json() == {
        "community_enabled": True,
        "messages_enabled": False,
    }

    response = client.patch(
        "/notification-preferences",
        json={"community_enabled": False},
    )
    assert response.status_code == 200
    assert response.get_json() == {
        "community_enabled": False,
        "messages_enabled": False,
    }
    assert calls == [17, 17]
    assert db.session.commits == 2
    assert MODULE_SOURCE.count("@require_csrf") >= 3
