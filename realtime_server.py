"""Socket.IO entrypoint for Prepza realtime study chat."""
import re
from datetime import datetime, timezone
from threading import Lock
from flask import request, session
from flask_socketio import SocketIO, emit, join_room, leave_room
from sqlalchemy import text
from app import app, db
import chat_interactions  # noqa: F401 - registers additive chat metadata hooks

# Socket.IO is the realtime transport; HTTP/database remains the source of truth.
socketio = SocketIO(app, async_mode="threading", cors_allowed_origins=[], logger=False, engineio_logger=False)
MESSAGE_PATH_RE = re.compile(r"^/chats/(\d+)/messages$")
_socket_rooms = {}
_socket_users = {}
_socket_state_lock = Lock()


def room_for(conversation_id):
    return f"chat:{conversation_id}"


def authenticated_user_id():
    value = session.get("user_id")
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


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
    user_id = authenticated_user_id()
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
    if not already_tracked and not had_other_socket:
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
    if not had_other_socket:
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
    emit("chat:read", {"conversation_id": conversation_id, "user_id": user_id, "read_at": read_at}, to=room_for(conversation_id), include_self=False)


@socketio.on("disconnect")
def handle_disconnect():
    rooms, user_id = socket_rooms_for_disconnect()
    if user_id is None:
        return
    for conversation_id in rooms:
        if not user_has_other_socket_in_room(user_id, conversation_id):
            emit("chat:presence", {"conversation_id": conversation_id, "user_id": user_id, "online": False}, to=room_for(conversation_id))


@app.after_request
def broadcast_message_response(response):
    """Broadcast only the persisted encrypted representation for E2EE chats."""
    match = MESSAGE_PATH_RE.match(request.path)
    if match and request.method == "POST" and 200 <= response.status_code < 300:
        try:
            conversation_id = int(match.group(1))
            if not is_e2ee_conversation(conversation_id):
                return response
            payload = safe_message_payload(response.get_json(silent=True))
            if payload and payload.get("conversation_id") == conversation_id:
                socketio.emit("chat:message", payload, to=room_for(conversation_id))
        except Exception:
            app.logger.exception("Realtime message broadcast failed")
    return response


@app.after_request
def normalize_chat_timestamps(response):
    """Expose database UTC timestamps with an explicit UTC offset.

    ChatMessage.created_at is stored as a naive UTC datetime for compatibility
    with the existing schema. Sending that value as a naive ISO string makes
    browsers interpret it as local time, which shifts the displayed chat time.
    Only chat-message payloads are normalized here; the stored value is not
    changed and the existing database schema remains untouched.
    """
    if request.method != "GET" or not re.match(r"^/chats/\d+/messages(?:/search)?$", request.path):
        return response
    if not response.is_json:
        return response
    try:
        payload = response.get_json(silent=True)
        if not isinstance(payload, dict) or not isinstance(payload.get("messages"), list):
            return response
        changed = False
        for message in payload["messages"]:
            if not isinstance(message, dict):
                continue
            for field in ("created_at", "edited_at"):
                value = message.get(field)
                if not isinstance(value, str) or not value:
                    continue
                try:
                    parsed = datetime.fromisoformat(value)
                except ValueError:
                    continue
                if parsed.tzinfo is None:
                    message[field] = parsed.replace(tzinfo=timezone.utc).isoformat()
                    changed = True
        if changed:
            response.set_data(__import__("json").dumps(payload, separators=(",", ":")))
            response.headers["Content-Type"] = "application/json"
    except Exception:
        app.logger.exception("Chat timestamp normalization failed")
    return response


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)
