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
    return [event for event in client.get_received() if event["name"] == name]


def _join(client, conversation_id):
    result = client.emit(
        "join_chat",
        {"conversation_id": conversation_id},
        callback=True,
    )
    assert result == {"ok": True, "conversation_id": conversation_id}


def test_socket_membership_and_same_conversation_delivery(realtime_world):
    conversation_id = realtime_world["conversation"].id
    sender = _socket_client(realtime_world["student_a"])
    receiver = _socket_client(realtime_world["student_b"])

    try:
        _join(sender, conversation_id)
        _join(receiver, conversation_id)

        outsider = _socket_client(realtime_world["admin"])
        try:
            denied = outsider.emit(
                "join_chat",
                {"conversation_id": conversation_id},
                callback=True,
            )
            assert denied == {
                "ok": False,
                "error": "Conversation unavailable",
            }
        finally:
            outsider.disconnect()

        sender.get_received()
        receiver.get_received()

        http = _http_client(realtime_world["student_a"])
        response = http.post(
            f"/chats/{conversation_id}/messages",
            json={
                "body": "c2lwaGVydGV4dA==",
                "nonce": "cXVhLW5vbmNl",
                "client_message_id": "qa-realtime-message-1",
            },
            headers=_csrf(realtime_world["student_a"].id),
        )
        assert response.status_code == 201, response.get_json()

        payload = response.get_json()
        assert payload["body"] == "c2lwaGVydGV4dA=="
        assert payload["nonce"] == "cXVhLW5vbmNl"

        delivered = _events(receiver, "chat:message")
        assert len(delivered) == 1
        assert delivered[0]["args"][0]["id"] == payload["id"]
        assert delivered[0]["args"][0]["body"] == payload["body"]
        assert delivered[0]["args"][0]["nonce"] == payload["nonce"]
    finally:
        sender.disconnect()
        receiver.disconnect()


def test_direct_e2ee_plaintext_is_rejected_before_persistence(realtime_world):
    conversation_id = realtime_world["conversation"].id
    http = _http_client(realtime_world["student_a"])

    response = http.post(
        f"/chats/{conversation_id}/messages",
        json={"body": "THIS IS PLAINTEXT"},
        headers=_csrf(realtime_world["student_a"].id),
    )
    assert response.status_code == 409
    assert "Plaintext direct messages are disabled" in response.get_json()["error"]

    count = db.session.query(Message).filter_by(
        conversation_id=conversation_id,
        body="THIS IS PLAINTEXT",
    ).count()
    assert count == 0


def test_chat_retry_is_idempotent_and_does_not_duplicate_message(realtime_world):
    conversation_id = realtime_world["conversation"].id
    http = _http_client(realtime_world["student_a"])
    payload = {
        "body": "cmV0cnktY2lwaGVydGV4dA==",
        "nonce": "cmV0cnktbm9uY2U=",
        "client_message_id": "qa-retry-stable-id",
    }

    first = http.post(
        f"/chats/{conversation_id}/messages",
        json=payload,
        headers=_csrf(realtime_world["student_a"].id),
    )
    second = http.post(
        f"/chats/{conversation_id}/messages",
        json=payload,
        headers=_csrf(realtime_world["student_a"].id),
    )

    assert first.status_code == 201, first.get_json()
    assert second.status_code == 200, second.get_json()
    assert second.get_json()["id"] == first.get_json()["id"]

    rows = Message.query.filter_by(
        conversation_id=conversation_id,
        sender_id=realtime_world["student_a"].id,
        body=payload["body"],
    ).all()
    assert len(rows) == 1


def test_offline_receiver_recovers_from_database_history(realtime_world):
    conversation_id = realtime_world["conversation"].id
    sender = _http_client(realtime_world["student_a"])

    response = sender.post(
        f"/chats/{conversation_id}/messages",
        json={
            "body": "b2ZmbGluZS1jaXBoZXJ0ZXh0",
            "nonce": "b2ZmbGluZS1ub25jZQ==",
            "client_message_id": "qa-offline-recovery-1",
        },
        headers=_csrf(realtime_world["student_a"].id),
    )
    assert response.status_code == 201

    receiver = _http_client(realtime_world["student_b"])
    history = receiver.get(f"/chats/{conversation_id}/messages")
    assert history.status_code == 200
    messages = history.get_json()["messages"]
    assert any(
        message["id"] == response.get_json()["id"]
        and message["body"] == "b2ZmbGluZS1jaXBoZXJ0ZXh0"
        for message in messages
    )


def test_socket_session_version_and_suspension_are_enforced(realtime_world):
    user = realtime_world["student_a"]
    from realtime_server import socketio

    flask_client = _http_client(user)
    client = socketio.test_client(app, flask_test_client=flask_client)
    assert client.is_connected()
    client.disconnect()

    user.session_version += 1
    db.session.commit()

    stale_client = socketio.test_client(app, flask_test_client=flask_client)
    assert not stale_client.is_connected()

    user.session_version += 1
    user.is_suspended = True
    db.session.commit()

    suspended_http = _http_client(user)
    suspended_socket = socketio.test_client(app, flask_test_client=suspended_http)
    assert not suspended_socket.is_connected()

    user.is_suspended = False
    db.session.commit()


def test_frontend_realtime_contract_matches_backend():
    root = Path(__file__).resolve().parents[1]
    frontend = (root / "frontend/src/crypto/chatRealtime.ts").read_text(
        encoding="utf-8"
    )
    backend = (root / "realtime_server.py").read_text(encoding="utf-8")

    for event in (
        "join_chat",
        "leave_chat",
        "chat:typing",
        "chat:read",
        "chat:message",
        "chat:message-updated",
        "chat:presence",
    ):
        assert event in frontend, f"frontend realtime event missing: {event}"
        assert event in backend, f"backend realtime event missing: {event}"

    assert "withCredentials: true" in frontend
    assert "reconnection: true" in frontend
    assert "reconnectionAttempts: Infinity" in frontend
    assert "socket.disconnect()" in frontend
    assert "client_message_id" in (
        root / "frontend/src/offline/chatOfflineQueue.ts"
    ).read_text(encoding="utf-8")


def test_realtime_deployment_contains_dedicated_chat_worker():
    root = Path(__file__).resolve().parents[1]
    compose = (root / "docker-compose.vps.yml").read_text(encoding="utf-8")
    worker = (root / "chat_event_worker.py").read_text(encoding="utf-8")

    assert "chat-worker:" in compose
    assert "python" in compose
    assert "chat_event_worker.py" in compose
    assert "REDIS_URL: redis://redis:6379/0" in compose
    assert "consume_forever(handle_event)" in worker
    assert 'channel="prepza-realtime"' in worker


def test_redis_stream_queue_is_not_treated_as_postgres_source_of_truth():
    root = Path(__file__).resolve().parents[1]
    queue = (root / "chat_event_queue.py").read_text(encoding="utf-8")
    realtime = (root / "realtime_server.py").read_text(encoding="utf-8")

    assert "PostgreSQL remains the source of truth" in queue
    assert "PostgreSQL has already committed the message" in realtime
    assert "xadd(" in queue
    assert "xack(" in queue
    assert "xautoclaim(" in queue
