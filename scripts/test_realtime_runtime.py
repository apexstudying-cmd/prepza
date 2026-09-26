"""Runtime regression checks for the authenticated Socket.IO study-chat boundary."""
import json
from unittest.mock import patch

from realtime_server import app, broadcast_message_response, socketio


def _session_client(user_id=None):
    flask_client = app.test_client()
    if user_id is not None:
        with flask_client.session_transaction() as session:
            session["user_id"] = user_id
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
    client = _session_client(7)
    assert client.is_connected()
    with patch("realtime_server.is_active_participant", return_value=False):
        assert client.emit("join_chat", {"conversation_id": 12}, callback=True) == {"ok": False, "error": "Conversation unavailable"}
        client.emit("chat:typing", {"conversation_id": 12, "typing": True})
        client.emit("chat:read", {"conversation_id": 12})
        assert client.get_received() == []
    client.disconnect()


def test_member_can_join_and_receive_presence():
    client = _session_client(7)
    assert client.is_connected()
    with patch("realtime_server.is_active_participant", return_value=True):
        assert client.emit("join_chat", {"conversation_id": 12}, callback=True) == {"ok": True, "conversation_id": 12}
        assert any(event["name"] == "chat:presence" for event in client.get_received())
    client.disconnect()


def test_repeated_join_does_not_duplicate_online_presence():
    observer = _session_client(8)
    subject = _session_client(7)
    with patch("realtime_server.is_active_participant", return_value=True):
        observer.emit("join_chat", {"conversation_id": 12}, callback=True)
        subject.emit("join_chat", {"conversation_id": 12}, callback=True)
        observer.get_received(); subject.get_received()
        subject.emit("join_chat", {"conversation_id": 12}, callback=True)
        assert not _event_named(observer.get_received(), "chat:presence")
    subject.disconnect(); observer.disconnect()


def test_disconnect_broadcasts_offline_presence():
    observer = _session_client(8)
    subject = _session_client(7)
    with patch("realtime_server.is_active_participant", return_value=True):
        observer.emit("join_chat", {"conversation_id": 12}, callback=True)
        subject.emit("join_chat", {"conversation_id": 12}, callback=True)
        observer.get_received(); subject.get_received()
        subject.disconnect()
        offline_events = _event_named(observer.get_received(), "chat:presence")
        assert offline_events[-1]["args"][0] == {"conversation_id": 12, "user_id": 7, "online": False}
    observer.disconnect()


def test_multiple_tabs_do_not_emit_offline_until_last_socket_disconnects():
    observer = _session_client(8)
    first_tab = _session_client(7)
    second_tab = _session_client(7)
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
        assert offline_events[-1]["args"][0] == {"conversation_id": 12, "user_id": 7, "online": False}
    observer.disconnect()


def test_explicit_leave_does_not_emit_offline_until_last_socket_leaves():
    observer = _session_client(8)
    first_tab = _session_client(7)
    second_tab = _session_client(7)
    with patch("realtime_server.is_active_participant", return_value=True):
        for client in (observer, first_tab, second_tab):
            assert client.emit("join_chat", {"conversation_id": 12}, callback=True)["ok"] is True
        observer.get_received(); first_tab.get_received(); second_tab.get_received()
        assert first_tab.emit("leave_chat", {"conversation_id": 12}, callback=True)["ok"] is True
        assert not _event_named(observer.get_received(), "chat:presence")
        assert second_tab.emit("leave_chat", {"conversation_id": 12}, callback=True)["ok"] is True
        offline_events = _event_named(observer.get_received(), "chat:presence")
        assert offline_events[-1]["args"][0] == {"conversation_id": 12, "user_id": 7, "online": False}
    first_tab.disconnect(); second_tab.disconnect(); observer.disconnect()


def test_two_members_receive_typing_read_and_persisted_message_events():
    sender = _session_client(7)
    receiver = _session_client(8)
    with patch("realtime_server.is_active_participant", return_value=True):
        sender.emit("join_chat", {"conversation_id": 12}, callback=True)
        receiver.emit("join_chat", {"conversation_id": 12}, callback=True)
        sender.get_received(); receiver.get_received()
        sender.emit("chat:typing", {"conversation_id": 12, "typing": True})
        typing_events = _event_named(receiver.get_received(), "chat:typing")
        assert typing_events[-1]["args"][0] == {"conversation_id": 12, "user_id": 7, "typing": True}
        assert not _event_named(sender.get_received(), "chat:typing")
        sender.emit("chat:read", {"conversation_id": 12, "read_at": "2026-09-13T10:00:00+00:00"})
        read_events = _event_named(receiver.get_received(), "chat:read")
        assert read_events[-1]["args"][0]["user_id"] == 7
        payload = {"message": {"id": 44, "conversation_id": 12, "body": "ciphertext-only", "sender_id": 7}}
        response = app.response_class(response=json.dumps(payload), status=201, mimetype="application/json")
        with app.test_request_context("/chats/12/messages", method="POST"):
            with patch("realtime_server.is_e2ee_conversation", return_value=True):
                assert broadcast_message_response(response) is response
        assert _event_named(receiver.get_received(), "chat:message")[-1]["args"][0] == payload["message"]
        assert _event_named(sender.get_received(), "chat:message")[-1]["args"][0] == payload["message"]
    sender.disconnect(); receiver.disconnect()


def test_leave_requires_membership():
    client = _session_client(7)
    with patch("realtime_server.is_active_participant", return_value=False):
        assert client.emit("leave_chat", {"conversation_id": 12}, callback=True) == {"ok": False}
    client.disconnect()


def test_message_broadcast_is_limited_to_e2ee_persisted_payload():
    payload = {"message": {"id": 44, "conversation_id": 12, "body": "ciphertext-only", "sender_id": 7}}
    response = app.response_class(response=json.dumps(payload), status=201, mimetype="application/json")
    with app.test_request_context("/chats/12/messages", method="POST"):
        with patch("realtime_server.is_e2ee_conversation", return_value=True), patch("realtime_server.socketio.emit") as emit:
            assert broadcast_message_response(response) is response
        emit.assert_called_once_with("chat:message", payload["message"], to="chat:12", include_self=False)


def test_non_e2ee_message_is_not_broadcast():
    payload = {"message": {"id": 45, "conversation_id": 13, "body": "server-visible message", "sender_id": 7}}
    response = app.response_class(response=json.dumps(payload), status=201, mimetype="application/json")
    with app.test_request_context("/chats/13/messages", method="POST"):
        with patch("realtime_server.is_e2ee_conversation", return_value=False), patch("realtime_server.socketio.emit") as emit:
            assert broadcast_message_response(response) is response
        emit.assert_not_called()


def test_malformed_message_payload_is_not_broadcast():
    payload = {"message": {"id": "44", "conversation_id": 12, "body": "should not escape validation"}}
    response = app.response_class(response=json.dumps(payload), status=201, mimetype="application/json")
    with app.test_request_context("/chats/12/messages", method="POST"):
        with patch("realtime_server.is_e2ee_conversation", return_value=True), patch("realtime_server.socketio.emit") as emit:
            assert broadcast_message_response(response) is response
        emit.assert_not_called()


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
