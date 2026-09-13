"""Runtime regression checks for the authenticated Socket.IO study-chat boundary."""
import json
from unittest.mock import patch

from realtime_server import app, broadcast_message_response, socketio


def _session_client(user_id=None):
    flask_client = app.test_client()
    if user_id is not None:
        with flask_client.session_transaction() as session:
            session["user_id"] = user_id
    return socketio.test_client(app, flask_test_client=flask_client)


def test_unauthenticated_socket_is_rejected():
    client = _session_client()
    assert not client.is_connected()


def test_join_typing_and_read_require_membership():
    client = _session_client(7)
    assert client.is_connected()
    with patch("realtime_server.is_active_participant", return_value=False):
        assert client.emit("join_chat", {"conversation_id": 12}, callback=True) == {
            "ok": False,
            "error": "Conversation unavailable",
        }
        client.emit("chat:typing", {"conversation_id": 12, "typing": True})
        client.emit("chat:read", {"conversation_id": 12})
        assert client.get_received() == []
    client.disconnect()


def test_member_can_join_and_receive_presence():
    client = _session_client(7)
    assert client.is_connected()
    with patch("realtime_server.is_active_participant", return_value=True):
        assert client.emit("join_chat", {"conversation_id": 12}, callback=True) == {
            "ok": True,
            "conversation_id": 12,
        }
        events = client.get_received()
        assert any(event["name"] == "chat:presence" for event in events)
    client.disconnect()


def test_leave_requires_membership():
    client = _session_client(7)
    assert client.is_connected()
    with patch("realtime_server.is_active_participant", return_value=False):
        assert client.emit("leave_chat", {"conversation_id": 12}, callback=True) == {"ok": False}
    client.disconnect()


def test_message_broadcast_is_limited_to_e2ee_persisted_payload():
    payload = {
        "message": {
            "id": 44,
            "conversation_id": 12,
            "body": "ciphertext-only",
            "sender_id": 7,
        }
    }
    response = app.response_class(
        response=json.dumps(payload), status=201, mimetype="application/json"
    )
    with app.test_request_context("/chats/12/messages", method="POST"):
        with patch("realtime_server.is_e2ee_conversation", return_value=True), patch(
            "realtime_server.socketio.emit"
        ) as emit:
            returned = broadcast_message_response(response)
        assert returned is response
        emit.assert_called_once_with("chat:message", payload["message"], to="chat:12")


def test_non_e2ee_message_is_not_broadcast():
    payload = {
        "message": {
            "id": 45,
            "conversation_id": 13,
            "body": "server-visible message",
            "sender_id": 7,
        }
    }
    response = app.response_class(
        response=json.dumps(payload), status=201, mimetype="application/json"
    )
    with app.test_request_context("/chats/13/messages", method="POST"):
        with patch("realtime_server.is_e2ee_conversation", return_value=False), patch(
            "realtime_server.socketio.emit"
        ) as emit:
            returned = broadcast_message_response(response)
        assert returned is response
        emit.assert_not_called()


def test_malformed_message_payload_is_not_broadcast():
    payload = {
        "message": {
            "id": "44",
            "conversation_id": 12,
            "body": "should not escape validation",
        }
    }
    response = app.response_class(
        response=json.dumps(payload), status=201, mimetype="application/json"
    )
    with app.test_request_context("/chats/12/messages", method="POST"):
        with patch("realtime_server.is_e2ee_conversation", return_value=True), patch(
            "realtime_server.socketio.emit"
        ) as emit:
            returned = broadcast_message_response(response)
        assert returned is response
        emit.assert_not_called()


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
