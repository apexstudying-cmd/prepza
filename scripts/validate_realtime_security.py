"""Static regression checks for the Socket.IO realtime security boundary."""
from pathlib import Path

SOURCE = Path("realtime_server.py").read_text(encoding="utf-8")

REQUIRED = {
    "authenticated socket gate": 'user_id = authenticated_user_id()\n    if user_id is None:',
    "join membership gate": 'if conversation_id <= 0 or not is_active_participant(user_id, conversation_id):\n        return {"ok": False, "error": "Conversation unavailable"}',
    "leave membership gate": 'if conversation_id <= 0 or not is_active_participant(user_id, conversation_id):\n        return {"ok": False}',
    "typing membership gate": 'if conversation_id <= 0 or not is_active_participant(user_id, conversation_id):\n        return',
    "read membership gate": 'if conversation_id <= 0 or not is_active_participant(user_id, conversation_id):\n        return',
    "E2EE broadcast gate": 'if not is_e2ee_conversation(conversation_id):\n                return response',
    "broadcast payload validation": 'payload = safe_message_payload(response.get_json(silent=True))',
}

for name, fragment in REQUIRED.items():
    if fragment not in SOURCE:
        raise SystemExit(f"Realtime security regression: missing {name}")

broadcast_start = SOURCE.index("def broadcast_message_response")
broadcast_body = SOURCE[broadcast_start:]
if "socketio.emit(\"chat:message\"" not in broadcast_body:
    raise SystemExit("Realtime security regression: message broadcast path disappeared")
if broadcast_body.index("is_e2ee_conversation") > broadcast_body.index("socketio.emit(\"chat:message\""):
    raise SystemExit("Realtime security regression: message broadcast is not E2EE-gated")

print("Realtime security invariants passed.")
