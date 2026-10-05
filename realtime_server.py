"""Socket.IO entrypoint for Prepza realtime study chat."""
import os
import re
from datetime import datetime, timezone
from threading import Lock
from flask import request, session
from flask_socketio import SocketIO, emit, join_room, leave_room
from sqlalchemy import text
import redis
from app import app, db, Conversation, ConversationParticipant
import chat_interactions  # noqa: F401 - registers additive chat metadata hooks
import chat_group_routes  # noqa: F401 - registers multi-user chat-group membership routes

# Socket.IO is the realtime transport; HTTP/database remains the source of truth.
REDIS_URL = os.environ.get("REDIS_URL")
# Flask-Limiter also uses REDIS_URL, but local QA deliberately sets it to
# memory://. That is a valid limiter/Kombu test transport, not a redis-py
# URL. Only real Redis URLs may enable realtime Redis presence/fan-out state.
REALTIME_REDIS_ENABLED = REDIS_URL.startswith(("redis://", "rediss://")) if REDIS_URL else False
REALTIME_REDIS_URL = REDIS_URL if REALTIME_REDIS_ENABLED else None
_realtime_redis = (
    redis.Redis.from_url(
        REALTIME_REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )
    if REALTIME_REDIS_URL
    else None
)

# Flask-SocketIO uses this queue to fan realtime events across multiple
# Render instances. PostgreSQL remains the message source of truth.
socketio = SocketIO(
    app,
    async_mode="threading",
    cors_allowed_origins=[],
    logger=False,
    engineio_logger=False,
    message_queue=REALTIME_REDIS_URL or None,
    channel="prepza-realtime",
)
MESSAGE_PATH_RE = re.compile(r"^/chats/(\d+)/messages$")
MESSAGE_ITEM_PATH_RE = re.compile(r"^/chats/(\d+)/messages/(\d+)$")
_socket_rooms = {}
_socket_users = {}
_socket_state_lock = Lock()


def room_for(conversation_id):
    return f"chat:{conversation_id}"


def _presence_key(conversation_id):
    return f"prepza:chat:presence:{conversation_id}"


def _redis_presence_join(user_id, conversation_id):
    if _realtime_redis is None:
        return None
    try:
        count = _realtime_redis.hincrby(_presence_key(conversation_id), str(user_id), 1)
        _realtime_redis.expire(_presence_key(conversation_id), 300)
        return count == 1
    except Exception:
        app.logger.exception("Redis presence join failed")
        return None


def _redis_presence_leave(user_id, conversation_id):
    if _realtime_redis is None:
        return None
    try:
        key = _presence_key(conversation_id)
        count = _realtime_redis.hincrby(key, str(user_id), -1)
        if count <= 0:
            _realtime_redis.hdel(key, str(user_id))
            count = 0
        if _realtime_redis.exists(key):
            _realtime_redis.expire(key, 300)
        return count == 0
    except Exception:
        app.logger.exception("Redis presence leave failed")
        return None


def authenticated_socket_user_id():
    """Authenticate the Socket.IO session against the same live session version as HTTP."""
    value = session.get("user_id")
    try:
        user_id = int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    if user_id is None:
        return None
    stamped_version = session.get("_session_version")
    from app import User
    user = db.session.get(User, user_id)
    if not user or user.is_suspended:
        return None
    if stamped_version is None or stamped_version != user.session_version:
        return None
    return user_id

def authenticated_user_id():
    return authenticated_socket_user_id()


def is_active_participant(user_id, conversation_id):
    row = db.session.execute(text(
        "SELECT 1 FROM conversation_participant "
        "WHERE conversation_id = :conversation_id AND user_id = :user_id "
        "AND left_at IS NULL LIMIT 1"
    ), {"conversation_id": conversation_id, "user_id": user_id}).first()
    return row is not None


def is_e2ee_conversation(conversation_id):
    row = db.session.execute(text(
        "SELECT e2ee_mode FROM conversation WHERE id = :conversation_id LIMIT 1"
    ), {"conversation_id": conversation_id}).first()
    return bool(row and row[0] in {"direct_v1", "group_v1"})


def safe_message_payload(response_json):
    if not isinstance(response_json, dict):
        return None
    message = response_json.get("message")
    if not isinstance(message, dict):
        message = response_json if "id" in response_json and "conversation_id" in response_json else None
    if not isinstance(message, dict):
        return None
    if not isinstance(message.get("id"), int) or not isinstance(message.get("conversation_id"), int):
        return None
    return message


def track_socket_room(conversation_id):
    with _socket_state_lock:
        _socket_rooms.setdefault(request.sid, set()).add(conversation_id)


def untrack_socket_room(conversation_id):
    with _socket_state_lock:
        rooms = _socket_rooms.get(request.sid)
        if not rooms:
            return
        rooms.discard(conversation_id)
        if not rooms:
            _socket_rooms.pop(request.sid, None)


def socket_rooms_for_disconnect():
    with _socket_state_lock:
        rooms = _socket_rooms.pop(request.sid, set())
        user_id = _socket_users.pop(request.sid, None)
        return rooms, user_id


def user_has_other_socket_in_room(user_id, conversation_id):
    with _socket_state_lock:
        for sid, rooms in _socket_rooms.items():
            if sid != request.sid and _socket_users.get(sid) == user_id and conversation_id in rooms:
                return True
    return False


@socketio.on("connect")
def handle_connect(auth=None):
    user_id = authenticated_socket_user_id()
    if user_id is None:
        return False
    with _socket_state_lock:
        _socket_rooms.setdefault(request.sid, set())
        _socket_users[request.sid] = user_id
    emit("realtime:ready", {"user_id": user_id})


@socketio.on("join_chat")
def handle_join_chat(data):
    user_id = authenticated_user_id()
    if user_id is None or not isinstance(data, dict):
        return {"ok": False, "error": "Authentication required"}
    try:
        conversation_id = int(data.get("conversation_id"))
    except (TypeError, ValueError):
        return {"ok": False, "error": "Invalid conversation"}
    if conversation_id <= 0 or not is_active_participant(user_id, conversation_id):
        return {"ok": False, "error": "Conversation unavailable"}
    room = room_for(conversation_id)
    already_tracked = False
    with _socket_state_lock:
        already_tracked = conversation_id in _socket_rooms.get(request.sid, set())
    had_other_socket = user_has_other_socket_in_room(user_id, conversation_id)
    join_room(room)
    track_socket_room(conversation_id)
    redis_first = None if already_tracked else _redis_presence_join(user_id, conversation_id)
    if not already_tracked and (redis_first is True or (redis_first is None and not had_other_socket)):
        emit("chat:presence", {"conversation_id": conversation_id, "user_id": user_id, "online": True}, to=room)
    return {"ok": True, "conversation_id": conversation_id}


@socketio.on("leave_chat")
def handle_leave_chat(data):
    user_id = authenticated_user_id()
    if user_id is None or not isinstance(data, dict):
        return {"ok": False}
    try:
        conversation_id = int(data.get("conversation_id"))
    except (TypeError, ValueError):
        return {"ok": False}
    if conversation_id <= 0 or not is_active_participant(user_id, conversation_id):
        return {"ok": False}
    room = room_for(conversation_id)
    had_other_socket = user_has_other_socket_in_room(user_id, conversation_id)
    leave_room(room)
    untrack_socket_room(conversation_id)
    redis_last = _redis_presence_leave(user_id, conversation_id)
    if redis_last is True or (redis_last is None and not had_other_socket):
        emit("chat:presence", {"conversation_id": conversation_id, "user_id": user_id, "online": False}, to=room)
    return {"ok": True, "conversation_id": conversation_id}


@socketio.on("chat:typing")
def handle_typing(data):
    user_id = authenticated_user_id()
    if user_id is None or not isinstance(data, dict):
        return
    try:
        conversation_id = int(data.get("conversation_id"))
    except (TypeError, ValueError):
        return
    if conversation_id <= 0 or not is_active_participant(user_id, conversation_id):
        return
    emit("chat:typing", {"conversation_id": conversation_id, "user_id": user_id, "typing": bool(data.get("typing"))}, to=room_for(conversation_id), include_self=False)


@socketio.on("chat:message-updated")
def handle_message_updated(data):
    user_id = authenticated_user_id()
    if user_id is None or not isinstance(data, dict):
        return
    try:
        conversation_id = int(data.get("conversation_id"))
        message_id = int(data.get("message_id"))
    except (TypeError, ValueError):
        return
    if conversation_id <= 0 or message_id <= 0 or not is_active_participant(user_id, conversation_id):
        return
    row = db.session.execute(text("SELECT id FROM message WHERE id = :message_id AND conversation_id = :conversation_id LIMIT 1"), {"message_id": message_id, "conversation_id": conversation_id}).first()
    if row is None:
        return
    emit("chat:message-updated", {"conversation_id": conversation_id, "message_id": message_id, "deleted": bool(data.get("deleted"))}, to=room_for(conversation_id), include_self=False)


@socketio.on("chat:read")
def handle_read(data):
    user_id = authenticated_user_id()
    if user_id is None or not isinstance(data, dict):
        return
    try:
        conversation_id = int(data.get("conversation_id"))
    except (TypeError, ValueError):
        return
    if conversation_id <= 0 or not is_active_participant(user_id, conversation_id):
        return
    read_at = data.get("read_at")
    if not isinstance(read_at, str) or not read_at.strip():
        read_at = datetime.now(timezone.utc).isoformat()
    try:
        setting = db.session.execute(
            text('SELECT read_receipts_enabled FROM "user" WHERE id = :user_id'),
            {"user_id": user_id},
        ).scalar()
    except Exception:
        db.session.rollback()
        setting = True
    if setting is False:
        return
    emit("chat:read", {"conversation_id": conversation_id, "user_id": user_id, "read_at": read_at}, to=room_for(conversation_id), include_self=False)


@socketio.on("disconnect")
def handle_disconnect():
    rooms, user_id = socket_rooms_for_disconnect()
    if user_id is None:
        return
    for conversation_id in rooms:
        redis_last = _redis_presence_leave(user_id, conversation_id)
        if redis_last is True or (redis_last is None and not user_has_other_socket_in_room(user_id, conversation_id)):
            emit("chat:presence", {"conversation_id": conversation_id, "user_id": user_id, "online": False}, to=room_for(conversation_id))




if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)