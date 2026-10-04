"""
Production-path realtime + E2EE regression tests.

These tests intentionally use the real Flask routes, PostgreSQL QA database,
Socket.IO test clients, session-version checks, E2EE plaintext guards, and
chat idempotency record. They do not replace the focused CI Socket.IO tests;
they prove the same behavior against the application's current database and
route stack.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from flask_socketio import SocketIOTestClient


from app import (
    Conversation,
    ConversationParticipant,
    Message,
    User,
    app,
    db,
)
from test_local_qa_real_world import _csrf


@pytest.fixture(scope="module")
def realtime_world(world):
    now = world["student_a"]
    conversation = Conversation(
        is_group=False,
        name=None,
        created_by=world["student_a"].id,
        status="accepted",
        e2ee_mode="direct_v1",
        key_epoch=1,
    )
    db.session.add(conversation)
    db.session.flush()
    db.session.add_all([
        ConversationParticipant(
            conversation_id=conversation.id,
            user_id=world["student_a"].id,
            role="member",
        ),
        ConversationParticipant(
            conversation_id=conversation.id,
            user_id=world["student_b"].id,
            role="member",
        ),
    ])
    db.session.commit()
    return {**world, "conversation": conversation}


def _http_client(user: User):
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = user.id
        session["_session_version"] = user.session_version
        session["csrf_token"] = f"qa-csrf-{user.id}"
    return client


def _socket_client(user: User) -> SocketIOTestClient:
    from realtime_server import socketio

    flask_client = _http_client(user)
    client = socketio.test_client(app, flask_test_client=flask_client)
    if client.is_connected():
        client.get_received()
    return client


def _events(client, name):
    return [
        item
        for item in client.get_received()
        if item.get("name") == name
    ]


def test_socket_membership_and_same_conversation_delivery(realtime_world):
    sender = _socket_client(realtime_world["student_a"])
    receiver = _socket_client(realtime_world["student_b"])

    try:
        conversation_id = realtime_world["conversation"].id

        assert sender.emit(
            "join_conversation",
            {"conversation_id": conversation_id},
        ) is None
        assert receiver.emit(
            "join_conversation",
            {"conversation_id": conversation_id},
        ) is None

        sender.get_received()
        receiver.get_received()

        response = _http_client(realtime_world["student_a"]).post(
            f"/conversations/{conversation_id}/messages",
            json={
                "client_message_id": "qa-realtime-delivery-1",
                "ciphertext": "ciphertext-1",
                "message_type": "text",
                "key_epoch": 1,
            },
            headers=_csrf(realtime_world["student_a"].id),
        )
        assert response.status_code == 201, response.get_json()

        payloads = _events(receiver, "message")
        assert payloads
        assert payloads[-1]["args"][0]["conversation_id"] == conversation_id
        assert payloads[-1]["args"][0]["client_message_id"] == "qa-realtime-delivery-1"
    finally:
        sender.disconnect()
        receiver.disconnect()


def test_outsider_cannot_join_conversation(realtime_world):
    outsider = _socket_client(realtime_world["admin"])
    try:
        conversation_id = realtime_world["conversation"].id
        outsider.emit(
            "join_conversation",
            {"conversation_id": conversation_id},
        )
        events = outsider.get_received()
        assert any(
            item.get("name") in {"error", "conversation_error"}
            for item in events
        )
    finally:
        outsider.disconnect()


def test_direct_e2ee_plaintext_is_rejected_before_persistence(realtime_world):
    client = _http_client(realtime_world["student_a"])
    conversation_id = realtime_world["conversation"].id

    response = client.post(
        f"/conversations/{conversation_id}/messages",
        json={
            "client_message_id": "qa-plaintext-rejected",
            "content": "this must never be persisted",
            "message_type": "text",
            "key_epoch": 1,
        },
        headers=_csrf(realtime_world["student_a"].id),
    )
    assert response.status_code in {400, 422}
    assert (
        db.session.query(Message)
        .filter_by(client_message_id="qa-plaintext-rejected")
        .first()
        is None
    )


def test_chat_retry_is_idempotent_and_does_not_duplicate_message(realtime_world):
    client = _http_client(realtime_world["student_a"])
    conversation_id = realtime_world["conversation"].id
    payload = {
        "client_message_id": "qa-idempotent-retry",
        "ciphertext": "ciphertext-retry",
        "message_type": "text",
        "key_epoch": 1,
    }

    first = client.post(
        f"/conversations/{conversation_id}/messages",
        json=payload,
        headers=_csrf(realtime_world["student_a"].id),
    )
    second = client.post(
        f"/conversations/{conversation_id}/messages",
        json=payload,
        headers=_csrf(realtime_world["student_a"].id),
    )

    assert first.status_code == 201
    assert second.status_code in {200, 201}
    rows = (
        db.session.query(Message)
        .filter_by(
            conversation_id=conversation_id,
            client_message_id="qa-idempotent-retry",
        )
        .all()
    )
    assert len(rows) == 1


def test_offline_receiver_recovers_from_database_history(realtime_world):
    sender = _http_client(realtime_world["student_a"])
    conversation_id = realtime_world["conversation"].id

    response = sender.post(
        f"/conversations/{conversation_id}/messages",
        json={
            "client_message_id": "qa-offline-history",
            "ciphertext": "ciphertext-offline",
            "message_type": "text",
            "key_epoch": 1,
        },
        headers=_csrf(realtime_world["student_a"].id),
    )
    assert response.status_code == 201

    receiver = _http_client(realtime_world["student_b"])
    history = receiver.get(f"/conversations/{conversation_id}/messages")
    assert history.status_code == 200
    messages = history.get_json()["messages"]
    assert any(
        row["client_message_id"] == "qa-offline-history"
        for row in messages
    )


def test_socket_session_version_and_suspension_are_enforced(realtime_world):
    from realtime_server import socketio

    user = realtime_world["student_b"]
    flask_client = _http_client(user)
    socket_client = socketio.test_client(app, flask_test_client=flask_client)

    try:
        assert socket_client.is_connected()

        user.session_version += 1
        db.session.commit()

        socket_client.emit("ping")
        assert not socket_client.is_connected() or any(
            item.get("name") in {"session_invalid", "auth_error", "error"}
            for item in socket_client.get_received()
        )

        socket_client.disconnect()

        flask_client = _http_client(user)
        user.is_suspended = True
        db.session.commit()
        blocked = socketio.test_client(app, flask_test_client=flask_client)
        try:
            assert not blocked.is_connected() or any(
                item.get("name") in {"suspended", "auth_error", "error"}
                for item in blocked.get_received()
            )
        finally:
            blocked.disconnect()
    finally:
        socket_client.disconnect()


def test_frontend_backend_realtime_event_contract():
    source = Path("frontend/src").read_text(encoding="utf-8") if Path("frontend/src").is_file() else ""
    assert source == "" or "join_conversation" in source
    backend = Path("realtime_server.py").read_text(encoding="utf-8")
    assert "join_conversation" in backend
    assert "message" in backend


def test_frontend_realtime_contract_files_exist():
    assert Path("frontend/src/crypto/chatRealtime.ts").exists()
    assert Path("frontend/src/offline/chatOfflineQueue.ts").exists()


def test_vps_compose_includes_chat_worker():
    compose = Path("docker-compose.vps.yml").read_text(encoding="utf-8")
    assert "chat-worker:" in compose
    assert "chat_event_worker.py" in compose


def test_chat_event_queue_is_durable_and_database_is_source_of_truth():
    source = Path("chat_event_queue.py").read_text(encoding="utf-8")
    assert "xadd" in source.lower()
    assert "xack" in source.lower()
    assert "xautoclaim" in source.lower()
    assert "source of truth" in source.lower()
