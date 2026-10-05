"""Real multi-process Redis -> realtime -> Socket.IO client runtime check.

This test intentionally uses the real Docker Redis service, the real
chat_event_worker.py process, and the separate realtime service. It creates
disposable authenticated users/conversation state, connects a real
python-socketio client to the realtime container, injects one controlled event
into an isolated Redis Stream, and verifies the connected client receives it.

It does not replace the existing authenticated in-process realtime tests; it
covers the missing distributed hop between the worker, Redis Socket.IO queue,
separate realtime process, and an actual Socket.IO client.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from contextlib import suppress

import redis
import socketio
from werkzeug.security import generate_password_hash

from app import app, db, User, Conversation, ConversationParticipant


REDIS_URL = os.environ.get("REDIS_URL", "")
REALTIME_URL = os.environ.get("PREPZA_REALTIME_TEST_URL", "http://realtime:5000")
STREAM = f"prepza:test:browser:{uuid.uuid4().hex}"
GROUP = f"prepza-test-browser-{uuid.uuid4().hex}"
CONSUMER = f"browser-test-{uuid.uuid4().hex}"
CHANNEL = "prepza-realtime"
EVENT_NAME = "chat:message"
PASSWORD = "Runtime!Test123"


def fail(message):
    raise AssertionError(message)


def wait_until(predicate, timeout=12.0, interval=0.1):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def signed_session_cookie(user):
    serializer = app.session_interface.get_signing_serializer(app)
    if serializer is None:
        fail("Flask session serializer is unavailable")
    return serializer.dumps({
        "_permanent": True,
        "user_id": user.id,
        "_session_version": user.session_version,
    })


def main():
    if not REDIS_URL.startswith(("redis://", "rediss://")):
        fail("REDIS_URL must point to the real Redis service (redis:// or rediss://)")

    redis_client = redis.Redis.from_url(
        REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=10,
    )
    redis_client.ping()

    users = {}
    worker = None
    clients = []
    conversation_id = None
    stream_id = None

    with app.app_context():
        suffix = uuid.uuid4().hex
        for role in ("primary", "peer"):
            user = User(
                email=f"runtime.browser.{role}.{suffix}@test.invalid",
                password_hash=generate_password_hash(PASSWORD),
                year=2,
                semester=1,
                display_name=f"Runtime browser {role}",
                email_verified=True,
                is_admin=False,
                is_suspended=False,
                profile_visibility="public",
                who_can_message="everyone",
                who_can_follow="everyone",
                read_receipts_enabled=True,
                university_id=None,
                program_id=None,
                session_version=0,
            )
            db.session.add(user)
            users[role] = user
        db.session.flush()

        conversation = Conversation(
            is_group=False,
            name=None,
            created_by=users["primary"].id,
            status="accepted",
            e2ee_mode="direct_v1",
            key_epoch=0,
        )
        db.session.add(conversation)
        db.session.flush()
        conversation_id = conversation.id

        db.session.add_all([
            ConversationParticipant(
                conversation_id=conversation.id,
                user_id=users["primary"].id,
                role="member",
            ),
            ConversationParticipant(
                conversation_id=conversation.id,
                user_id=users["peer"].id,
                role="member",
            ),
        ])
        db.session.commit()

        cookie = signed_session_cookie(users["peer"])

        env = os.environ.copy()
        env.update({
            "REDIS_URL": REDIS_URL,
            "PREPZA_CHAT_EVENT_STREAM": STREAM,
            "PREPZA_CHAT_EVENT_GROUP": GROUP,
            "PREPZA_CHAT_EVENT_CONSUMER": CONSUMER,
        })
        worker = subprocess.Popen(
            [sys.executable, "chat_event_worker.py"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        try:
            group_ready = wait_until(
                lambda: bool(redis_client.exists(STREAM))
                and any(
                    item["name"] == GROUP
                    for item in redis_client.xinfo_groups(STREAM)
                ),
                timeout=8,
            )
            if not group_ready:
                fail("chat_event_worker did not create the isolated Redis consumer group")

            received = []
            client = socketio.Client(
                reconnection=False,
                logger=False,
                engineio_logger=False,
            )
            clients.append(client)

            @client.on(EVENT_NAME)
            def on_chat_message(payload):
                received.append(payload)

            cookie_name = app.config.get("SESSION_COOKIE_NAME", "session")
            client.connect(
                REALTIME_URL,
                headers={"Cookie": f"{cookie_name}={cookie}"},
                transports=["polling"],
                wait_timeout=8,
            )

            if not client.connected:
                fail("real Socket.IO client could not connect to the separate realtime service")

            join_result = client.call(
                "join_chat",
                {"conversation_id": conversation_id},
                timeout=8,
            )
            if join_result != {"ok": True, "conversation_id": conversation_id}:
                fail(f"authenticated client could not join test conversation: {join_result!r}")

            payload = {
                "id": f"cross-process-{uuid.uuid4().hex}",
                "conversation_id": conversation_id,
                "body": "ciphertext-only",
                "sender_id": users["primary"].id,
            }
            stream_id = redis_client.xadd(
                STREAM,
                {
                    "event": EVENT_NAME,
                    "conversation_id": str(conversation_id),
                    "payload": json.dumps(payload, separators=(",", ":")),
                    "created_at": str(time.time()),
                },
            )

            if not wait_until(lambda: any(item == payload for item in received), timeout=12):
                fail(
                    "connected Socket.IO client did not receive the Redis-worker event "
                    f"for conversation {conversation_id}"
                )

            pending = redis_client.xpending(STREAM, GROUP)
            if pending["pending"] != 0:
                fail(f"Redis event was delivered but remains pending: {pending!r}")

            print("PASS: real Socket.IO client connected to the separate realtime process")
            print("PASS: authenticated client joined the real database-backed conversation")
            print("PASS: Redis Stream -> chat-worker -> Redis Socket.IO queue -> realtime process -> client delivered chat:message")
            print(f"PASS: Redis stream entry {stream_id} was acknowledged")
        finally:
            for client in clients:
                with suppress(Exception):
                    client.disconnect()
            if worker is not None:
                with suppress(Exception):
                    worker.terminate()
                with suppress(Exception):
                    worker.wait(timeout=5)

            with suppress(Exception):
                redis_client.delete(STREAM)
            with suppress(Exception):
                redis_client.xgroup_destroy(STREAM, GROUP)

            db.session.rollback()
            for user in users.values():
                with suppress(Exception):
                    db.session.delete(user)
            with suppress(Exception):
                db.session.commit()


if __name__ == "__main__":
    main()
