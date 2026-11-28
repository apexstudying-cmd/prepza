from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from flask import Flask

from group_routes import register_group_routes

ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")
REGISTRY_SOURCE = (ROOT / "route_registry.py").read_text(encoding="utf-8")
MODULE_SOURCE = (ROOT / "group_routes.py").read_text(encoding="utf-8")


def test_app_delegates_all_group_routes_to_the_group_feature_module() -> None:
    assert "register_group_routes(" in APP_SOURCE
    assert 'from group_routes import register_group_routes as register' in REGISTRY_SOURCE
    assert "def _serialize_group(" not in APP_SOURCE
    assert "def _get_group_visible(" not in APP_SOURCE
    assert "from app import" not in MODULE_SOURCE
    for route in (
        '@app.route("/groups", methods=["POST"])',
        '@app.route("/groups")',
        '@app.route("/groups/mine")',
        '@app.route("/groups/<int:group_id>")',
        '@app.route("/groups/<int:group_id>/join", methods=["POST"])',
        '@app.route("/groups/<int:group_id>/leave", methods=["POST"])',
        '@app.route("/groups/<int:group_id>/posts", methods=["POST"])',
        '@app.route("/groups/<int:group_id>/posts")',
        '@app.route("/groups/<int:group_id>/posts/<int:post_id>")',
        '@app.route("/groups/<int:group_id>/posts/<int:post_id>/comments", methods=["POST"])',
        '@app.route("/groups/<int:group_id>/posts/<int:post_id>/comments/<int:comment_id>/helpful", methods=["POST"])',
        '@app.route("/groups/<int:group_id>/posts/<int:post_id>/like", methods=["POST"])',
        '@app.route("/groups/<int:group_id>/posts/<int:post_id>/like", methods=["DELETE"])',
        '@app.route("/groups/<int:group_id>/posts/<int:post_id>/vote", methods=["POST"])',
        '@app.route("/groups/<int:group_id>/posts/<int:post_id>/vote", methods=["DELETE"])',
        '@app.route("/groups/<int:group_id>/members")',
        '@app.route("/groups/<int:group_id>/members/<int:target_user_id>", methods=["PATCH"])',
        '@app.route("/groups/<int:group_id>/members/<int:target_user_id>", methods=["DELETE"])',
        '@app.route("/groups/<int:group_id>/files", methods=["POST"])',
        '@app.route("/groups/<int:group_id>/files")',
        '@app.route("/groups/<int:group_id>/files/<int:file_id>", methods=["DELETE"])',
    ):
        assert route not in APP_SOURCE
        assert route in MODULE_SOURCE


def test_group_registration_preserves_private_group_visibility_and_route_methods() -> None:
    app = Flask("prepza-group-routes-contract")
    app.config.update(TESTING=True, SECRET_KEY="group-routes-contract-secret")

    class Group:
        privacy = "private"

    class GroupMember:
        class Query:
            def filter_by(self, **_kwargs):
                return self
            def first(self):
                return None
        query = Query()

    class FakeSession:
        def get(self, model, group_id):
            return Group() if model is Group and group_id == 55 else None

    db = SimpleNamespace(session=FakeSession())
    identity = lambda function: function

    register_group_routes(
        app,
        db,
        Group=Group,
        GroupMember=GroupMember,
        GroupPost=object(),
        GroupPostComment=object(),
        GroupPostLike=object(),
        GroupQuestionVote=object(),
        GroupFile=object(),
        User=object(),
        Notification=object(),
        University=object(),
        Program=object(),
        Document=object(),
        XP_COMMUNITY_HELPFUL_REPLY=20,
        award_xp=lambda *_args, **_kwargs: None,
        check_and_unlock_achievements=lambda *_args, **_kwargs: None,
        _display_name=lambda user: "Student",
        get_signed_url=lambda *_args, **_kwargs: None,
        should_notify=lambda *_args: False,
        send_push_notification=lambda *_args, **_kwargs: None,
        require_csrf=identity,
    )

    routes = {}
    for rule in app.url_map.iter_rules():
        routes.setdefault(rule.rule, set()).update(rule.methods)
    assert "POST" in routes["/groups"]
    assert "GET" in routes["/groups"]
    assert "GET" in routes["/groups/<int:group_id>/posts"]
    assert "POST" in routes["/groups/<int:group_id>/posts"]
    assert "PATCH" in routes["/groups/<int:group_id>/members/<int:target_user_id>"]
    assert "DELETE" in routes["/groups/<int:group_id>/files/<int:file_id>"]
    assert MODULE_SOURCE.count("@require_csrf") == 14

    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 17
    response = client.get("/groups/55")
    assert response.status_code == 404
