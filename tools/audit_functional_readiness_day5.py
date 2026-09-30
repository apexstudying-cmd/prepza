"""Day 5 functional wiring audit.

This is intentionally static: it protects runtime contracts that ordinary
typechecking/py_compile cannot prove, especially retry/idempotency wiring and
the real frontend build entrypoint.
"""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text(encoding="utf-8")
MAIN = (ROOT / "frontend/src/main.tsx").read_text(encoding="utf-8")
QUEUE = (ROOT / "frontend/src/offline/chatOfflineQueue.ts").read_text(encoding="utf-8")
CHAT = (ROOT / "frontend/src/crypto/WhatsAppChatExperience.tsx").read_text(encoding="utf-8")
PACKAGE = json.loads((ROOT / "frontend/package.json").read_text(encoding="utf-8"))

checks = {
    "SES change-email boto3 import": "\nimport boto3\n" in APP and "boto3.client(" in APP,
    "chat idempotency schema": "_ensure_chat_idempotency_schema" in APP and "chat_message_idempotency" in APP,
    "chat client_message_id validation": "client_message_id=data.get(" in APP and "client_message_id must be a string" in APP,
    "chat idempotency conflict handling": "ON CONFLICT (conversation_id,sender_id,client_message_id) DO NOTHING" in APP,
    "offline queue creates stable message id": "payload.client_message_id = crypto.randomUUID()" in QUEUE,
    "online chat creates stable message id": "client_message_id: crypto.randomUUID()" in CHAT,
    "frontend mounts App": "<App />" in MAIN,
    "external document import is mounted": "<ExternalDocumentImport />" in MAIN,
    "package has real build script": bool(PACKAGE.get("scripts", {}).get("build")) and "vite build" in PACKAGE.get("scripts", {}).get("build", ""),
    "package prebuild is explicit": "prebuild" in PACKAGE.get("scripts", {}),
}
failed=[name for name,ok in checks.items() if not ok]
print("DAY5_FUNCTIONAL_WIRING_AUDIT")
for name,ok in checks.items():
    print(("PASS " if ok else "FAIL ")+name)
if failed:
    raise SystemExit("Day 5 functional wiring audit failed: " + "; ".join(failed))
print("Day 5 functional wiring audit passed.")
