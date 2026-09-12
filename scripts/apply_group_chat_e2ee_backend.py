"""Apply the group-chat E2EE backend foundation to app.py.

Safety properties:
- idempotent: every change checks its anchor/marker before editing;
- does not migrate data or generate keys server-side;
- stores only per-member encrypted key envelopes;
- does not expose another member's envelope;
- keeps the existing message API shape (body + nonce).

Run from the repository root AFTER migrations/add_group_chat_e2ee.sql has
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
old = '''    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)\n    # updated_at is bumped on every new message so /chats can sort by\n'''
new = '''    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)\n    # E2EE protocol metadata. "direct_v1" uses the existing 1:1 client\n    # encryption; "group_v1" uses a client-generated symmetric group key\n    # distributed as per-member encrypted envelopes. "legacy" is retained\n    # only for old rows until the migration classifies them.\n    e2ee_mode = db.Column(db.String(20), nullable=False, default="legacy")\n    key_epoch = db.Column(db.Integer, nullable=False, default=0)\n    # updated_at is bumped on every new message so /chats can sort by\n'''
replace_once(old, new, "conversation e2ee metadata")

# 2. Envelope model directly after Message and before attachments.
anchor = '''class MessageAttachment(db.Model):\n'''
model = '''class ConversationKeyEnvelope(db.Model):\n    """\n    One encrypted copy of a client-generated group conversation key for\n    one recipient and one key epoch. The server never receives the\n    plaintext group key and cannot unwrap this without the recipient's\n    device private key.\n    """\n    id = db.Column(db.Integer, primary_key=True)\n    conversation_id = db.Column(db.Integer, db.ForeignKey("conversation.id", ondelete="CASCADE"), nullable=False)\n    recipient_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)\n    sender_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)\n    key_epoch = db.Column(db.Integer, nullable=False, default=0)\n    version = db.Column(db.Integer, nullable=False, default=1)\n    nonce = db.Column(db.String(64), nullable=False)\n    ciphertext = db.Column(db.Text, nullable=False)\n    created_at = db.Column(db.DateTime, default=datetime.utcnow)\n    __table_args__ = (\n        db.UniqueConstraint(\n            "conversation_id", "recipient_user_id", "key_epoch",\n            name="uq_conversation_key_envelope_recipient_epoch",\n        ),\n    )\n\n\n'''
replace_once(anchor, model + anchor, "conversation key envelope model")

# 3. New group chats opt into group_v1 immediately; direct chats keep direct_v1.
old = '''    conversation = Conversation(\n        is_group=is_group,\n        name=name if is_group else None,\n        created_by=user_id,\n        status=conversation_status,\n    )\n'''
new = '''    conversation = Conversation(\n        is_group=is_group,\n        name=name if is_group else None,\n        created_by=user_id,\n        status=conversation_status,\n        e2ee_mode="group_v1" if is_group else "direct_v1",\n        key_epoch=0,\n    )\n'''
replace_once(old, new, "group create e2ee mode")

# 4. Add secure envelope APIs before message listing.
anchor = '''@app.route("/chats/<int:conversation_id>/messages")\ndef list_messages(conversation_id):\n'''
insert = '''GROUP_E2EE_MAX_ENVELOPES_PER_REQUEST = 100\nGROUP_E2EE_CIPHERTEXT_MAX = 10000\nGROUP_E2EE_NONCE_MAX = 128\n\n\ndef _serialize_key_envelope(envelope):\n    return {\n        "conversation_id": envelope.conversation_id,\n        "recipient_user_id": envelope.recipient_user_id,\n        "sender_user_id": envelope.sender_user_id,\n        "key_epoch": envelope.key_epoch,\n        "version": envelope.version,\n        "nonce": envelope.nonce,\n        "ciphertext": envelope.ciphertext,\n        "created_at": envelope.created_at.isoformat() if envelope.created_at else None,\n    }\n\n\n@app.route("/chats/<int:conversation_id>/key-envelopes", methods=["POST"])\n@limiter.limit("60 per hour")\n@require_csrf\ndef upload_group_key_envelopes(conversation_id):\n    """Store encrypted group-key envelopes without ever seeing the group key."""\n    user_id = session.get("user_id")\n    if not user_id:\n        return jsonify({"error": "Not logged in"}), 401\n\n    if not _active_participant(conversation_id, user_id):\n        return jsonify({"error": "Conversation not found"}), 404\n\n    conversation = db.session.get(Conversation, conversation_id)\n    if not conversation or not conversation.is_group:\n        return jsonify({"error": "Group conversation not found"}), 404\n    if conversation.e2ee_mode != "group_v1":\n        return jsonify({"error": "This conversation is not using group E2EE"}), 409\n\n    data = request.get_json(silent=True) or {}\n    envelopes = data.get("envelopes")\n    if not isinstance(envelopes, list) or not envelopes:\n        return jsonify({"error": "envelopes must be a non-empty list"}), 400\n    if len(envelopes) > GROUP_E2EE_MAX_ENVELOPES_PER_REQUEST:\n        return jsonify({"error": "Too many envelopes in one request"}), 400\n\n    active_members = {\n        p.user_id\n        for p in ConversationParticipant.query.filter_by(\n            conversation_id=conversation_id, left_at=None\n        ).all()\n    }\n\n    stored = []\n    for item in envelopes:\n        if not isinstance(item, dict):\n            return jsonify({"error": "Each envelope must be an object"}), 400\n        recipient = item.get("recipient_user_id")\n        sender = item.get("sender_user_id")\n        epoch = item.get("key_epoch", conversation.key_epoch)\n        version = item.get("version", 1)\n        nonce = (item.get("nonce") or "").strip()\n        ciphertext = (item.get("ciphertext") or "").strip()\n\n        if not isinstance(recipient, int) or isinstance(recipient, bool) or recipient not in active_members:\n            return jsonify({"error": "recipient_user_id must be an active group member"}), 400\n        if sender != user_id:\n            return jsonify({"error": "sender_user_id must match the authenticated user"}), 403\n        if epoch != conversation.key_epoch:\n            return jsonify({"error": "Envelope key_epoch is stale"}), 409\n        if version != 1:\n            return jsonify({"error": "Unsupported envelope version"}), 400\n        if not nonce or len(nonce) > GROUP_E2EE_NONCE_MAX:\n            return jsonify({"error": "Invalid envelope nonce"}), 400\n        if not ciphertext or len(ciphertext) > GROUP_E2EE_CIPHERTEXT_MAX:\n            return jsonify({"error": "Invalid envelope ciphertext"}), 400\n\n        existing = ConversationKeyEnvelope.query.filter_by(\n            conversation_id=conversation_id,\n            recipient_user_id=recipient,\n            key_epoch=epoch,\n        ).first()\n        if existing:\n            # Idempotent/retry-safe: only the original sender can replace\n            # an envelope for the same recipient/epoch.\n            if existing.sender_user_id != user_id:\n                return jsonify({"error": "Envelope already exists"}), 409\n            existing.nonce = nonce\n            existing.ciphertext = ciphertext\n            existing.version = version\n            stored.append(existing)\n        else:\n            envelope = ConversationKeyEnvelope(\n                conversation_id=conversation_id,\n                recipient_user_id=recipient,\n                sender_user_id=user_id,\n                key_epoch=epoch,\n                version=version,\n                nonce=nonce,\n                ciphertext=ciphertext,\n            )\n            db.session.add(envelope)\n            stored.append(envelope)\n\n    db.session.commit()\n    return jsonify({"envelopes": [_serialize_key_envelope(e) for e in stored]}), 201\n\n\n@app.route("/chats/<int:conversation_id>/key-envelopes")\ndef list_group_key_envelopes(conversation_id):\n    """Return only the logged-in member's encrypted key envelope."""\n    user_id = session.get("user_id")\n    if not user_id:\n        return jsonify({"error": "Not logged in"}), 401\n    if not _active_participant(conversation_id, user_id):\n        return jsonify({"error": "Conversation not found"}), 404\n\n    conversation = db.session.get(Conversation, conversation_id)\n    if not conversation or not conversation.is_group:\n        return jsonify({"error": "Group conversation not found"}), 404\n\n    envelopes = ConversationKeyEnvelope.query.filter_by(\n        conversation_id=conversation_id,\n        recipient_user_id=user_id,\n        key_epoch=conversation.key_epoch,\n    ).order_by(ConversationKeyEnvelope.created_at.desc()).all()\n\n    return jsonify({\n        "conversation_id": conversation_id,\n        "key_epoch": conversation.key_epoch,\n        "e2ee_mode": conversation.e2ee_mode,\n        "envelopes": [_serialize_key_envelope(e) for e in envelopes],\n    })\n\n\n''' + anchor
replace_once(anchor, insert, "group key envelope routes")

# 5. Do not advertise server-side ciphertext search for encrypted chats.
old = '''    q = (request.args.get("q") or "").strip()\n    if not q:\n        return jsonify({"messages": []})\n\n    messages = (\n'''
new = '''    q = (request.args.get("q") or "").strip()\n    if not q:\n        return jsonify({"messages": []})\n\n    conversation = db.session.get(Conversation, conversation_id)\n    if conversation and conversation.e2ee_mode in ("direct_v1", "group_v1"):\n        return jsonify({\n            "error": "Encrypted conversations must be searched on-device",\n            "search_mode": "client",\n        }), 409\n\n    messages = (\n'''
replace_once(old, new, "disable server-side e2ee search")

APP.write_text(text, encoding="utf-8")
print("Group chat E2EE backend patch complete.")
