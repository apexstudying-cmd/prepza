"""Post-commit chat realtime dispatch helpers.

HTTP/database persistence remains the source of truth. These helpers are
called explicitly after a successful commit so realtime_server.py does not
need to register Flask hooks when it is imported.
"""

import os


def _redis_enabled():
    value = (os.environ.get("REDIS_URL") or "").strip()
    return value.startswith(("redis://", "rediss://"))


def dispatch_message(conversation_id, payload):
    """Queue or directly emit a newly committed E2EE chat message."""
    if not isinstance(payload, dict):
        return
    if _redis_enabled():
        from chat_event_queue import enqueue_chat_event
        enqueue_chat_event(
            event="chat:message",
            conversation_id=conversation_id,
            payload=payload,
        )
        return

    # Local/single-instance fallback. Import lazily so app.py never imports
    # realtime_server while that module is constructing its Socket.IO object.
    from realtime_server import room_for, socketio
    socketio.emit("chat:message", payload, to=room_for(conversation_id))


def dispatch_message_update(conversation_id, message_id, deleted):
    """Queue or directly emit a committed chat edit/delete event."""
    payload = {
        "conversation_id": conversation_id,
        "message_id": message_id,
        "deleted": bool(deleted),
    }
    if _redis_enabled():
        from chat_event_queue import enqueue_chat_event
        enqueue_chat_event(
            event="chat:message-updated",
            conversation_id=conversation_id,
            payload=payload,
        )
        return

    from realtime_server import room_for, socketio
    socketio.emit(
        "chat:message-updated",
        payload,
        to=room_for(conversation_id),
        include_self=False,
    )
