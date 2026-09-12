"""Safely register the standalone group-E2EE routes in app.py.

Run from the repository root after the database migration and the existing
backend E2EE patch have been applied. The patch is fail-closed and idempotent.
"""

from pathlib import Path

APP = Path("app.py")
IMPORT_ANCHOR = "from urllib.parse import urlencode\n"
DB_ANCHOR = "db = SQLAlchemy(app)\n"
MAIN_ANCHOR = 'if __name__ == "__main__":'

text = APP.read_text(encoding="utf-8")

if "from e2ee_chat_routes import register_e2ee_chat_routes" in text:
    print("E2EE route registration already present; nothing to do.")
    raise SystemExit(0)

if text.count(IMPORT_ANCHOR) != 1:
    raise SystemExit("Expected one import anchor; refusing to modify app.py")
if text.count(DB_ANCHOR) != 1:
    raise SystemExit("Expected one SQLAlchemy anchor; refusing to modify app.py")
main_index = text.find(MAIN_ANCHOR)
if main_index < 0:
    raise SystemExit("Could not find __main__ server block; refusing to modify app.py")
if "class ConversationKeyEnvelope" not in text:
    raise SystemExit("ConversationKeyEnvelope model is not present; run the backend E2EE patch first")
if "class ConversationParticipant" not in text or "class Conversation" not in text or "class User" not in text:
    raise SystemExit("Required conversation/user models are missing; refusing to modify app.py")

text = text.replace(
    IMPORT_ANCHOR,
    IMPORT_ANCHOR + "from e2ee_chat_routes import register_e2ee_chat_routes\n",
    1,
)

registration = (
    "\n# Prepza group-chat E2EE HTTP routes.\n"
    "register_e2ee_chat_routes(\n"
    "    app, db, Conversation, ConversationParticipant, User, ConversationKeyEnvelope\n"
    ")\n"
)

main_index = text.find(MAIN_ANCHOR)
text = text[:main_index] + registration + "\n" + text[main_index:]
APP.write_text(text, encoding="utf-8")
print("Registered group-chat E2EE routes before the server startup block.")
