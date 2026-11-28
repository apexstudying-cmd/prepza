from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

from flask import Flask

from chat_read_routes import register_chat_read_routes
from route_registry import register_chat_read_routes as register_chat_read_routes_from_registry

ROOT = Path(__file__).resolve().parents[1]


class FakeColumn:
    def __init__(self, name: str):
        self.name = name

    def desc(self):
        return ("desc", self.name)

    def __lt__(self, value):
        return ("lt", self.name, value)


class FakeMessageQuery:
    def __init__(self, rows):
        self.rows = rows
        self.filters = []
        self.ordering = None
        self.limit_value = None

    def filter_by(self, **kwargs):
        self.filters.append(("filter_by", kwargs))
        return self

    def filter(self, expression):
        self.filters.append(("filter", expression))
        return self

    def order_by(self, *expressions):
        self.ordering = expressions
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def all(self):
        return list(self.rows)


class FakeMessage:
    id = FakeColumn("id")
    created_at = FakeColumn("created_at")


def make_app(query):
    app = Flask("prepza-chat-read-routes-contract")
    app.secret_key = "test-only"
    FakeMessage.query = query
    calls = []

    def get_chat_or_404(conversation_id, user_id):
        calls.append((conversation_id, user_id))
        return SimpleNamespace(id=conversation_id) if conversation_id == 44 and user_id == 7 else None

    register_chat_read_routes(
        app,
        Message=FakeMessage,
        chat_page_size=2,
        get_chat_or_404=get_chat_or_404,
        serialize_conversation_detail=lambda conversation, viewer_id: {
            "id": conversation.id,
            "viewer_id": viewer_id,
        },
        serialize_chat_message=lambda message: {"id": message.id},
    )
    return app, calls


def test_chat_read_routes_preserve_auth_membership_payload_and_route_contract():
    query = FakeMessageQuery([])
    app, calls = make_app(query)
    routes = {
        rule.endpoint: (rule.rule, frozenset(rule.methods - {"HEAD", "OPTIONS"}))
        for rule in app.url_map.iter_rules()
        if rule.endpoint != "static"
    }
    assert routes == {
        "get_chat": ("/chats/<int:conversation_id>", frozenset({"GET"})),
        "list_chat_messages": ("/chats/<int:conversation_id>/messages", frozenset({"GET"})),
    }

    client = app.test_client()
    assert client.get("/chats/44").status_code == 401
    assert client.get("/chats/44/messages").status_code == 401
    assert calls == []

    with client.session_transaction() as session:
        session["user_id"] = 7

    detail = client.get("/chats/44")
    assert detail.status_code == 200
    assert detail.get_json() == {"id": 44, "viewer_id": 7}
    assert client.get("/chats/99").get_json() == {"error": "Conversation not found"}
    assert calls == [(44, 7), (99, 7)]


def test_chat_message_history_keeps_before_id_order_and_page_limit():
    rows = [SimpleNamespace(id=3), SimpleNamespace(id=2)]
    query = FakeMessageQuery(rows)
    app, calls = make_app(query)
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 7

    response = client.get("/chats/44/messages?before_id=100")
    assert response.status_code == 200
    assert response.get_json() == {"messages": [{"id": 2}, {"id": 3}]}
    assert calls == [(44, 7)]
    assert query.filters == [
        ("filter_by", {"conversation_id": 44}),
        ("filter", ("lt", "id", 100)),
    ]
    assert query.ordering == (("desc", "created_at"), ("desc", "id"))
    assert query.limit_value == 2


def test_chat_read_route_registry_forwards_explicit_dependencies(monkeypatch):
    app = Flask("prepza-chat-read-registry-contract")
    dependencies = {
        "Message": object(),
        "chat_page_size": 50,
        "get_chat_or_404": object(),
        "serialize_conversation_detail": object(),
        "serialize_chat_message": object(),
    }
    calls = {}
    module = ModuleType("chat_read_routes")

    def register(target_app, **kwargs):
        calls["args"] = (target_app,)
        calls["kwargs"] = kwargs

    module.register_chat_read_routes = register
    monkeypatch.setitem(sys.modules, "chat_read_routes", module)

    register_chat_read_routes_from_registry(app, **dependencies)

    assert calls == {"args": (app,), "kwargs": dependencies}


def test_app_keeps_chat_read_routes_at_the_original_registration_point():
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    registry_source = (ROOT / "route_registry.py").read_text(encoding="utf-8")
    workflow_source = (ROOT / ".github" / "workflows" / "backend-extension-contract.yml").read_text(encoding="utf-8")

    assert "from route_registry import (" in app_source
    assert "    register_chat_read_routes," in app_source
    assert "def get_chat(" not in app_source
    assert "def list_chat_messages(" not in app_source
    assert "from chat_read_routes import register_chat_read_routes as register" in registry_source
    assert "chat_read_routes.py" in workflow_source
    assert "tests/test_chat_read_routes_contract.py" in workflow_source

    create_chat = app_source.index("def create_chat():")
    registration = app_source.rindex("register_chat_read_routes(")
    next_write_route = app_source.index('@app.post("/chats/<int:conversation_id>/messages")')
    assert create_chat < registration < next_write_route
