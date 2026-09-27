"""Durable Redis Stream queue for persisted chat events.

PostgreSQL remains the source of truth for messages. Socket.IO is the low-latency
transport. This stream sits between message persistence and realtime/side-effect
delivery so bursts do not require the HTTP request to perform every downstream
operation synchronously.
"""
from __future__ import annotations

import json
import os
import socket
import time
from typing import Any

import redis

STREAM_KEY = os.environ.get("PREPZA_CHAT_EVENT_STREAM", "prepza:chat:events")
GROUP_NAME = os.environ.get("PREPZA_CHAT_EVENT_GROUP", "prepza-chat-delivery")
CONSUMER_NAME = os.environ.get("PREPZA_CHAT_EVENT_CONSUMER", socket.gethostname())


def _client():
    url = os.environ.get("REDIS_URL")
    if not url:
        raise RuntimeError("REDIS_URL is required for the dedicated chat event queue")
    return redis.Redis.from_url(url, decode_responses=True, socket_connect_timeout=2, socket_timeout=5)


def ensure_group(client=None):
    client = client or _client()
    try:
        client.xgroup_create(STREAM_KEY, GROUP_NAME, id="0", mkstream=True)
    except redis.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def enqueue_chat_event(*, event: str, conversation_id: int, payload: dict[str, Any]) -> str:
    client = _client()
    return str(client.xadd(
        STREAM_KEY,
        {
            "event": event,
            "conversation_id": str(int(conversation_id)),
            "payload": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            "created_at": str(time.time()),
        },
        maxlen=100000,
        approximate=True,
    ))


def decode_event(fields: dict[str, str]) -> dict[str, Any]:
    return {
        "event": fields.get("event"),
        "conversation_id": int(fields["conversation_id"]),
        "payload": json.loads(fields.get("payload") or "{}"),
        "created_at": float(fields.get("created_at") or 0),
    }


def consume_forever(handler):
    client = _client()
    ensure_group(client)
    while True:
        batches = client.xreadgroup(
            GROUP_NAME,
            CONSUMER_NAME,
            {STREAM_KEY: ">"},
            count=50,
            block=5000,
        )
        for _, entries in batches:
            for message_id, fields in entries:
                try:
                    handler(message_id, decode_event(fields))
                    client.xack(STREAM_KEY, GROUP_NAME, message_id)
                except Exception:
                    # Leave failed entries pending for retry/inspection.
                    raise
