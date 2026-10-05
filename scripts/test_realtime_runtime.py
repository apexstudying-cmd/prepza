"""Runtime regression checks for the authenticated Socket.IO study-chat boundary."""
import pytest
from unittest.mock import patch

from realtime_server import app, socketio
from chat_realtime_dispatch import dispatch_message
from runtime_test_fixtures import runtime_test_users

_USERS = {}


@pytest.fixture(scope="module", autouse=True)
def runtime_users():
    with runtime_test_users() as users:
        _USERS.update(users)
        yield users
    _USERS.clear()


def _session_client(role=None):
    flask_client = app.test_client()
    if role is not None:
        user = _USERS[role]
        with flask_client.session_transaction() as session:
            session["user_id"] = user.id
            session["_session_version"] = user.session_version
    client = socketio.test_client(app, flask_test_client=flask_client)
    if client.is_connected():
        client.get_received()
    return client


def _event_named(events, name):
    return [event for event in events if event["name"] == name]


def test_unauthenticated_socket_is_rejected():
    client = _session_client()
    assert not client.is_connected()


def test_join_typing_and_read_require_membership():
    client = _session_client("primary")
    assert client.is_connected()
    with patch("realtime_server.is_active_participant", return_value=False):
        assert client.emit("join_chat", {"conversation_id": 12}, callback=True) == {"ok": False, "error": "Conversation unavailable"}
        client.emit("chat:typing", {"conversation_id": 12, "typing": True})
        client.emit("chat:read", {"conversation_id": 12})
        assert client.get_received() == []
    client.disconnect()


def test_member_can_join_and_receive_presence():
    client = _session_client("primary")
    assert client.is_connected()
    with patch("realtime_server.is_active_participant", return_value=True):
        assert client.emit("join_chat", {"conversation_id": 12}, callback=True) == {"ok": True, "conversation_id": 12}
        assert any(event["name"] == "chat:presence" for event in client.get_received())
    client.disconnect()


def test_repeated_join_does_not_duplicate_online_presence():
    observer = _session_client("peer")
    subject = _session_client("primary")
    with patch("realtime_server.is_active_participant", return_value=True):
        observer.emit("join_chat", {"conversation_id": 12}, callback=True)
        subject.emit("join_chat", {"conversation_id": 12}, callback=True)
        observer.get_received(); subject.get_received()
        subject.emit("join_chat", {"conversation_id": 12}, callback=True)
        assert not _event_named(observer.get_received(), "chat:presence")
    subject.disconnect(); observer.disconnect()


def test_disconnect_broadcasts_offline_presence():
    observer = _session_client("peer")
    subject = _session_client("primary")
    with patch("realtime_server.is_active_participant", return_value=True):
        observer.emit("join_chat", {"conversation_id": 12}, callback=True)
        subject.emit("join_chat", {"conversation_id": 12}, callback=True)
        observer.get_received(); subject.get_received()
        subject.disconnect()
        offline_events = _event_named(observer.get_received(), "chat:presence")
        assert offline_events[-1]["args"][0] == {"conversation_id": 12, "user_id": _USERS["primary"].id, "online": False}
    observer.disconnect()


def test_multiple_tabs_do_not_emit_offline_until_last_socket_disconnects():
    observer = _session_client("peer")
    first_tab = _session_client("primary")
    second_tab = _session_client("primary")
    with patch("realtime_server.is_active_participant", return_value=True):
        for client in (observer, first_tab, second_tab):
            assert client.emit("join_chat", {"conversation_id": 12}, callback=True)["ok"] is True
        # Drain the observer after all joins so the assertion below concerns
        # the disconnect operation rather than the initial online event.
        observer.get_received(); first_tab.get_received(); second_tab.get_received()
        first_tab.disconnect()
        assert not _event_named(observer.get_received(), "chat:presence")
        second_tab.disconnect()
        offline_events = _event_named(observer.get_received(), "chat:presence")
        assert offline_events[-1]["args"][0] == {"conversation_id": 12, "user_id": _USERS["primary"].id, "online": False}
    observer.disconnect()


def test_explicit_leave_does_not_emit_offline_until_last_socket_leaves():
    observer = _session_client("peer")
    first_tab = _session_client("primary")
    second_tab = _session_client("primary")
    with patch("realtime_server.is_active_participant", return_value=True):
        for client in (observer, first_tab, second_tab):
            assert client.emit("join_chat", {"conversation_id": 12}, callback=True)["ok"] is True
        observer.get_received(); first_tab.get_received(); second_tab.get_received()
        assert first_tab.emit("leave_chat", {"conversation_id": 12}, callback=True)["ok"] is True
        assert not _event_named(observer.get_received(), "chat:presence")
        assert second_tab.emit("leave_chat", {"conversation_id": 12}, callback=True)["ok"] is True
        offline_events = _event_named(observer.get_received(), "chat:presence")
        assert offline_events[-1]["args"][0] == {"conversation_id": 12, "user_id": _USERS["primary"].id, "online": False}
    first_tab.disconnect(); second_tab.disconnect(); observer.disconnect()


def test_two_members_receive_typing_read_and_persisted_message_events():
    sender = _session_client("primary")
    receiver = _session_client("peer")
    with patch("realtime_server.is_active_participant", return_value=True):
        sender.emit("join_chat", {"conversation_id": 12}, callback=True)
        receiver.emit("join_chat", {"conversation_id": 12}, callback=True)
        sender.get_received(); receiver.get_received()
        sender.emit("chat:typing", {"conversation_id": 12, "typing": True})
        typing_events = _event_named(receiver.get_received(), "chat:typing")
        assert typing_events[-1]["args"][0] == {"conversation_id": 12, "user_id": _USERS["primary"].id, "typing": True}
        assert not _event_named(sender.get_received(), "chat:typing")
        sender.emit("chat:read", {"conversation_id": 12, "read_at": "2026-09-13T10:00:00+00:00"})
        read_events = _event_named(receiver.get_received(), "chat:read")
        assert read_events[-1]["args"][0]["user_id"] == _USERS["primary"].id
        payload = {
            "id": 44,
            "conversation_id": 12,
            "body": "ciphertext-only",
            "sender_id": _USERS["primary"].id,
        }
        dispatch_message(12, payload)
        assert _event_named(receiver.get_received(), "chat:message")[-1]["args"][0] == payload
        assert _event_named(sender.get_received(), "chat:message")[-1]["args"][0] == payload
    sender.disconnect(); receiver.disconnect()


def test_leave_requires_membership():
    client = _session_client("primary")
    with patch("realtime_server.is_active_participant", return_value=False):
        assert client.emit("leave_chat", {"conversation_id": 12}, callback=True) == {"ok": False}
    client.disconnect()




if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
