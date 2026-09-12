"""Safely register the group E2EE routes in app.py.

Run this script once from the repository root. It refuses to modify app.py
unless every expected integration anchor is present and the integration has
not already been applied. It creates a backup before writing.
"""

from pathlib import Path

APP = Path("app.py")
BACKUP = Path("app.py.e2ee-backup")
IMPORT_ANCHOR = "from urllib.parse import urlencode\n"
MODEL_ANCHOR = "db = SQLAlchemy(app)\n"
REGISTRATION_ANCHOR = "db = SQLAlchemy(app)\n"

text = APP.read_text(encoding="utf-8")

if "register_e2ee_chat_routes" in text:
    raise SystemExit("E2EE chat routes already registered; refusing to patch twice.")

if IMPORT_ANCHOR not in text:
    raise SystemExit("Missing import anchor; app.py was not changed.")
if MODEL_ANCHOR not in text:
    raise SystemExit("Missing SQLAlchemy anchor; app.py was not changed.")

new_text = text.replace(
    IMPORT_ANCHOR,
    IMPORT_ANCHOR
    + "from e2ee_chat_models import create_e2ee_models\n"
    + "from e2ee_chat_routes import register_e2ee_chat_routes\n",
    1,
)

new_text = new_text.replace(
    MODEL_ANCHOR,
    MODEL_ANCHOR
    + "\n# Group-chat E2EE envelope model is defined against this app's SQLAlchemy instance.\n"
    + "ConversationKeyEnvelope = create_e2ee_models(db)\n",
    1,
)

# Route registration is intentionally appended immediately after the model\n# setup anchor. Flask only needs the models to exist before registration;\n# endpoint execution happens after the full module has loaded.\nregistration = (\n    "\n# Prepza group-chat E2EE routes.\n"
    "register_e2ee_chat_routes(\n"
    "    app, db, Conversation, ConversationParticipant, User, ConversationKeyEnvelope\n"
    ")\n"
)

# The Conversation models are defined later in app.py, so register at the\n# end of the module rather than beside db initialization.\nnew_text += registration

BACKUP.write_text(text, encoding="utf-8")
APP.write_text(new_text, encoding="utf-8")
print("Patched app.py and created app.py.e2ee-backup")
