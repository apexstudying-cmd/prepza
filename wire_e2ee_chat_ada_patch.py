"""Safely wire the prebuilt E2EE chat/Ada modules into app.py.

This is intentionally a local patch script, not an import-time migration.
Run it from the repository root, review the resulting diff, then commit it.
"""

import io
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_PATH = ROOT / "app.py"
CHAT_ROUTES_PATH = ROOT / "e2ee_chat_routes.py"


def read_preserving_newlines(path: Path):
    with io.open(path, "r", encoding="utf-8", newline="") as handle:
        raw = handle.read()
    newline = "\r\n" if "\r\n" in raw else "\n"
    logical = raw.replace("\r\n", "\n").replace("\r", "\n")
    return logical, newline


def write_preserving_newlines(path: Path, logical: str, newline: str):
    output = logical.replace("\n", newline)
    with io.open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(output)


def require_exactly_once(source: str, anchor: str, label: str):
    count = source.count(anchor)
    if count != 1:
        raise SystemExit(
            f"ABORT: expected exactly 1 {label}, found {count}. "
            "No files were written."
        )


def require_absent(source: str, fragment: str, label: str):
    count = source.count(fragment)
    if count:
        raise SystemExit(
            f"ABORT: {label} already exists ({count} occurrence(s)). "
            "No files were written."
        )


def main():
    if not APP_PATH.is_file() or not CHAT_ROUTES_PATH.is_file():
        raise SystemExit("ABORT: app.py or e2ee_chat_routes.py is missing. No files were written.")

    app, app_newline = read_preserving_newlines(APP_PATH)
    chat_routes, chat_newline = read_preserving_newlines(CHAT_ROUTES_PATH)

    # app.py must still be unwired and must contain the existing model classes
    # this patch passes into the registration functions.
    require_exactly_once(app, "from urllib.parse import urlencode\n", "app import anchor")
    require_exactly_once(app, "# ---------- Auth routes ----------\n", "app route anchor")
    for class_name in ("User", "Conversation", "ConversationParticipant", "Document"):
        require_exactly_once(app, f"class {class_name}(db.Model):\n", f"{class_name} model definition")

    for fragment, label in (
        ("from e2ee_chat_models import create_e2ee_models", "create_e2ee_models import"),
        ("from e2ee_chat_routes import register_e2ee_chat_routes", "register_e2ee_chat_routes import"),
        ("from e2ee_ada_routes import register_e2ee_ada_route", "register_e2ee_ada_route import"),
        ("ConversationKeyEnvelope = create_e2ee_models(db)", "ConversationKeyEnvelope assignment"),
        ("register_e2ee_chat_routes(\n", "E2EE chat route registration"),
        ("register_e2ee_ada_route(\n", "E2EE Ada route registration"),
    ):
        require_absent(app, fragment, label)

    # e2ee_chat_routes.py was written before app.py's existing UserKey routes
    # became canonical. Do not register duplicate /keys handlers. The group
    # E2EE endpoints and plaintext guard remain in this module.
    require_exactly_once(
        chat_routes,
        "    # Identity-key bootstrap. The private key never leaves the browser; the\n",
        "legacy identity-key route block start",
    )
    require_exactly_once(chat_routes, '    @app.post("/keys/register")\n', "legacy /keys/register route")
    require_exactly_once(chat_routes, '    @app.get("/keys/<int:user_id>")\n', "legacy /keys/<user_id> route")
    require_exactly_once(
        chat_routes,
        "    if not getattr(app, \"_prepza_e2ee_plaintext_guard\", False):\n",
        "group plaintext guard anchor",
    )
    require_exactly_once(
        chat_routes,
        "def register_e2ee_chat_routes(app, db, Conversation, ConversationParticipant, User, ConversationKeyEnvelope):\n",
        "E2EE chat registration function",
    )

    legacy_start = chat_routes.index(
        "    # Identity-key bootstrap. The private key never leaves the browser; the\n"
    )
    guard_start = chat_routes.index(
        "    if not getattr(app, \"_prepza_e2ee_plaintext_guard\", False):\n",
        legacy_start,
    )
    replacement = (
        "    # app.py already owns the authenticated UserKey implementation and its\n"
        "    # /keys/register and /keys/<user_id> routes. Keep this module focused\n"
        "    # on group E2EE state, envelopes, and the plaintext message guard.\n\n"
    )
    patched_chat_routes = chat_routes[:legacy_start] + replacement + chat_routes[guard_start:]

    imports = (
        "from urllib.parse import urlencode\n"
        "from e2ee_chat_models import create_e2ee_models\n"
        "from e2ee_chat_routes import register_e2ee_chat_routes\n"
        "from e2ee_ada_routes import register_e2ee_ada_route\n"
    )
    patched_app = app.replace("from urllib.parse import urlencode\n", imports, 1)

    registration = (
        "# ---------- E2EE chat + scoped Ada routes ----------\n"
        "# All application models are defined above this point. The E2EE model\n"
        "# is created exactly once, then the prebuilt route modules receive the\n"
        "# canonical app.py model/db objects.\n"
        "ConversationKeyEnvelope = create_e2ee_models(db)\n"
        "register_e2ee_chat_routes(\n"
        "    app, db, Conversation, ConversationParticipant, User, ConversationKeyEnvelope\n"
        ")\n"
        "register_e2ee_ada_route(\n"
        "    app, db, Conversation, ConversationParticipant, Document, User\n"
        ")\n\n\n"
    )
    patched_app = patched_app.replace("# ---------- Auth routes ----------\n", registration + "# ---------- Auth routes ----------\n", 1)

    # Final in-memory assertions before any write occurs.
    require_exactly_once(patched_app, "from e2ee_chat_models import create_e2ee_models\n", "new model import")
    require_exactly_once(patched_app, "ConversationKeyEnvelope = create_e2ee_models(db)\n", "new model creation")
    require_exactly_once(patched_app, "register_e2ee_chat_routes(\n", "new chat registration")
    require_exactly_once(patched_app, "register_e2ee_ada_route(\n", "new Ada registration")
    require_exactly_once(patched_chat_routes, "# app.py already owns the authenticated UserKey implementation", "duplicate-key replacement")
    if "/keys/register" in patched_chat_routes or "/keys/<int:user_id>" in patched_chat_routes:
        raise SystemExit("ABORT: duplicate /keys route text remains in e2ee_chat_routes.py. No files were written.")

    write_preserving_newlines(APP_PATH, patched_app, app_newline)
    write_preserving_newlines(CHAT_ROUTES_PATH, patched_chat_routes, chat_newline)
    print("Patch applied safely to app.py and e2ee_chat_routes.py.")
    print("Next: python3 -m py_compile app.py e2ee_chat_routes.py e2ee_ada_routes.py e2ee_chat_models.py")
    print("Then review: git diff -- app.py e2ee_chat_routes.py")


if __name__ == "__main__":
    main()
