"""Worker for the dedicated Prepza chat event stream.

Run this as a separate Render background worker when Redis is configured.
It publishes queued events through Flask-SocketIO's Redis message queue,
so multiple realtime servers can receive the same event without making
PostgreSQL or the request thread responsible for fan-out.
"""
from __future__ import annotations

import os

from flask_socketio import SocketIO

from app import app
from chat_event_queue import consume_forever

socketio = SocketIO(
    app,
    async_mode="threading",
    message_queue=os.environ.get("REDIS_URL"),
    channel="prepza-realtime",
)


def handle_event(_message_id, event):
    socketio.emit(
        event["event"],
        event["payload"],
        to=f"chat:{event['conversation_id']}",
    )


if __name__ == "__main__":
    if not os.environ.get("REDIS_URL"):
        raise RuntimeError("REDIS_URL is required for the chat event worker")
    consume_forever(handle_event)
