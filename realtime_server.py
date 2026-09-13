"""Socket.IO entrypoint for Prepza realtime study chat."""
import re
from datetime import datetime, timezone
from flask import request, session
from flask_socketio import SocketIO, emit, join_room, leave_room
from sqlalchemy import text
from app import app, db

# Socket.IO is the realtime transport; HTTP/database remains the source of truth.
socketio = SocketIO(app, async_mode="threading", cors_allowed_origins=[], logger=False, engineio_logger=False)
MESSAGE_PATH_RE = re.compile(r"^/chats/(\d+)/messages$")


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


@socketio.on("connect")
def handle_connect(auth=None):
    user_id = authenticated_user_id()
    if user_id is None:
        return False
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
    join_room(room)
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
    leave_room(room)
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
            # Realtime delivery must never turn a successful message request
            # into a failed request. HTTP history remains the source of truth.
            app.logger.exception("Realtime message broadcast failed")
    return response


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)
