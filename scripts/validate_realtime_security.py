"""Static regression checks for the current Socket.IO realtime security boundary."""
from pathlib import Path

SOURCE = Path("realtime_server.py").read_text(encoding="utf-8")
DISPATCH = Path("chat_realtime_dispatch.py").read_text(encoding="utf-8")
APP_SOURCE = Path("app.py").read_text(encoding="utf-8")
FRONTEND = Path("frontend/src/crypto/chatRealtime.ts").read_text(encoding="utf-8")

REQUIRED = {
    "authenticated socket gate": 'user_id = authenticated_socket_user_id()\n    if user_id is None:',
    "socket session version gate": 'stamped_version = session.get("_session_version")',
    "socket suspension gate": 'if not user or user.is_suspended:',
    "socket session mismatch gate": 'if stamped_version is None or stamped_version != user.session_version:',
    "join membership gate": 'if conversation_id <= 0 or not is_active_participant(user_id, conversation_id):\n        return {"ok": False, "error": "Conversation unavailable"}',
    "leave membership gate": 'if conversation_id <= 0 or not is_active_participant(user_id, conversation_id):\n        return {"ok": False}',
    "typing membership gate": 'if conversation_id <= 0 or not is_active_participant(user_id, conversation_id):\n        return',
    "read membership gate": 'if conversation_id <= 0 or not is_active_participant(user_id, conversation_id):\n        return',
}

for name, fragment in REQUIRED.items():
    if fragment not in SOURCE:
        raise SystemExit(f"Realtime security regression: missing {name}")

for fragment, name in [
    ('def dispatch_message(conversation_id, payload, *, e2ee_mode=None):', "post-commit dispatch helper"),
    ('if e2ee_mode in {"direct_v1", "group_v1"}:', "E2EE broadcast gate"),
    ('if isinstance(body, str) and body.strip() and not isinstance(nonce, str):\n            return', "ciphertext payload gate"),
    ('enqueue_chat_event(', "Redis event-queue dispatch"),
    ('socketio.emit("chat:message", payload, to=room_for(conversation_id))', "single-instance message emit"),
]:
    if fragment not in DISPATCH:
        raise SystemExit(f"Realtime security regression: missing {name}")

for fragment, name in [
    ('if conversation.e2ee_mode == "direct_v1" and body and not nonce:', "direct E2EE send gate"),
    ('if conversation.e2ee_mode == "group_v1" and body and not nonce:', "group E2EE send gate"),
    ('dispatch_message(conversation_id, _serialize_chat_message(message), e2ee_mode=conversation.e2ee_mode)', "mode-aware post-commit dispatch"),
]:
    if fragment not in APP_SOURCE:
        raise SystemExit(f"Realtime security regression: missing {name}")

for source, name, fragment in [
    (FRONTEND, "realtime teardown", "export function resetChatRealtime()"),
    (FRONTEND, "realtime socket disconnect", "socket.disconnect()"),
    (APP_SOURCE, "logout realtime teardown", "if (target === 'login') resetChatRealtime()"),
]:
    if fragment not in source:
        raise SystemExit(f"Realtime security regression: missing {name}")

print("Realtime security invariants passed.")
