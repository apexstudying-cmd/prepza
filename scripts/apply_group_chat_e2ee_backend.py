"""Safely apply the app.py pieces owned by the group-chat E2EE foundation.

Route handlers live in e2ee_chat_routes.py and are registered by the existing
prepza_control bootstrap. Keeping route ownership in one module avoids
 duplicate Flask URL rules and makes the integration idempotent.

Run from the repository root after migrations/add_group_chat_e2ee.sql has
been applied to the database:
    python scripts/apply_group_chat_e2ee_backend.py
"""

from pathlib import Path

APP = Path("app.py")
text = APP.read_text(encoding="utf-8")


def replace_once(old: str, new: str, label: str) -> None:
    global text
    if new in text:
        print(f"already applied: {label}")
        return
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly 1 anchor, found {count}")
    text = text.replace(old, new, 1)
    print(f"applied: {label}")


# 1. Conversation model: explicit E2EE protocol and key epoch.
replace_once(
    '''    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)\n    # updated_at is bumped on every new message so /chats can sort by\n''',
    '''    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)\n    # E2EE protocol metadata. "direct_v1" uses the existing 1:1 client\n    # encryption; "group_v1" uses a client-generated symmetric group key\n    # distributed as per-member encrypted envelopes. "legacy" is retained\n    # only for old rows until the migration classifies them.\n    e2ee_mode = db.Column(db.String(20), nullable=False, default="legacy")\n    key_epoch = db.Column(db.Integer, nullable=False, default=0)\n    # updated_at is bumped on every new message so /chats can sort by\n''',
    "conversation e2ee metadata",
)

# 2. Envelope model is owned by e2ee_chat_models.py. The standalone route
# module receives that model at registration time; do not duplicate it here.

# 3. New groups start at epoch 1 so the first client-generated key can be
# provisioned immediately. Direct chats keep the existing direct_v1 mode.
replace_once(
    '''    conversation = Conversation(\n        is_group=is_group,\n        name=name if is_group else None,\n        created_by=user_id,\n        status=conversation_status,\n    )\n''',
    '''    conversation = Conversation(\n        is_group=is_group,\n        name=name if is_group else None,\n        created_by=user_id,\n        status=conversation_status,\n        e2ee_mode="group_v1" if is_group else "direct_v1",\n        key_epoch=1 if is_group else 0,\n    )\n''',
    "group create e2ee mode",
)

# 4. Encrypted conversations must use on-device search. The server never
# searches message plaintext for direct_v1/group_v1 conversations.
replace_once(
    '''    q = (request.args.get("q") or "").strip()\n    if not q:\n        return jsonify({"messages": []})\n\n    messages = (\n''',
    '''    q = (request.args.get("q") or "").strip()\n    if not q:\n        return jsonify({"messages": []})\n\n    conversation = db.session.get(Conversation, conversation_id)\n    if conversation and conversation.e2ee_mode in ("direct_v1", "group_v1"):\n        return jsonify({\n            "error": "Encrypted conversations must be searched on-device",\n            "search_mode": "client",\n        }), 409\n\n    messages = (\n''',
    "disable server-side e2ee search",
)

APP.write_text(text, encoding="utf-8")
print("Group chat E2EE app.py foundation patch complete.")
