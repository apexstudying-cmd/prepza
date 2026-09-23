"""E2EE group-chat HTTP routes.

This module deliberately keeps all group-key material opaque to the server.
Only encrypted envelopes are accepted/stored. The route registration function
is called after the application's Conversation/User models are defined.
"""

from functools import wraps
import base64
import binascii
import re

from flask import jsonify, request, session
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


def register_e2ee_chat_routes(app, db, Conversation, ConversationParticipant, User, ConversationKeyEnvelope):
    def current_user_id():
        return session.get("user_id")

    def participant_for(conversation_id, user_id):
        return ConversationParticipant.query.filter_by(
            conversation_id=conversation_id,
            user_id=user_id,
            left_at=None,
        ).first()

    def e2ee_state(conversation_id):
        row = db.session.execute(
            text("SELECT e2ee_mode, key_epoch FROM conversation WHERE id = :conversation_id"),
            {"conversation_id": conversation_id},
        ).mappings().first()
        if not row:
            return "legacy", 0
        return row["e2ee_mode"] or "legacy", int(row["key_epoch"] or 0)

    def active_provisioner(conversation_id, epoch):
        """Return the only member allowed to publish a new epoch key."""
        row = db.session.execute(
            text(
                "SELECT c.created_by, cp.user_id "
                "FROM conversation c JOIN conversation_participant cp ON cp.conversation_id = c.id "
                "WHERE c.id = :conversation_id AND cp.left_at IS NULL ORDER BY cp.user_id ASC"
            ),
            {"conversation_id": conversation_id},
        ).all()
        if not row:
            return None
        creator_id = int(row[0][0]) if row[0][0] is not None else None
        active_ids = [int(item[1]) for item in row if item[1] is not None]
        if epoch == 1 and creator_id in active_ids:
            return creator_id
        return active_ids[0] if active_ids else None

    def require_member(view):
        @wraps(view)
        def wrapped(conversation_id, *args, **kwargs):
            user_id = current_user_id()
            if not user_id:
                return jsonify({"error": "Authentication required"}), 401
            conversation = Conversation.query.get(conversation_id)
            if not conversation:
                return jsonify({"error": "Conversation not found"}), 404
            if not participant_for(conversation_id, user_id):
                return jsonify({"error": "You are not a member of this conversation"}), 403
            return view(conversation, user_id, *args, **kwargs)
        return wrapped

    def decode_base64(value, label, max_bytes=None):
        if not isinstance(value, str) or not value or not re.fullmatch(r"[A-Za-z0-9+/]+={0,2}", value):
            raise ValueError(f"Invalid {label} encoding")
        try:
            raw = base64.b64decode(value, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError(f"Invalid {label} encoding")
        if max_bytes is not None and len(raw) > max_bytes:
            raise ValueError(f"{label} is too large")
        return raw

    @app.post("/keys/register")
    def register_e2ee_identity_key():
        user_id = current_user_id()
        if not user_id:
            return jsonify({"error": "Authentication required"}), 401
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or not isinstance(payload.get("public_key"), str):
            return jsonify({"error": "public_key is required"}), 400
        public_key = payload["public_key"].strip()
        if not public_key or len(public_key) > 128 or not re.fullmatch(r"[A-Za-z0-9_-]+", public_key):
            return jsonify({"error": "Invalid public_key"}), 400
        try:
            normalized = public_key.replace("-", "+").replace("_", "/")
            raw_public_key = base64.b64decode(normalized + "=" * ((4 - len(normalized) % 4) % 4), validate=True)
        except (ValueError, binascii.Error):
            return jsonify({"error": "Invalid public_key encoding"}), 400
        if len(raw_public_key) != 65 or raw_public_key[0] != 0x04:
            return jsonify({"error": "public_key must be an uncompressed P-256 public key"}), 400

        existing = db.session.execute(text("SELECT public_key FROM user_key WHERE user_id = :user_id"), {"user_id": user_id}).scalar_one_or_none()
        if existing:
            if existing == public_key:
                return jsonify({"ok": True, "already_registered": True})
            return jsonify({"error": "A different secure identity is already registered for this account", "code": "IDENTITY_KEY_REPLACEMENT_REQUIRED"}), 409

        db.session.execute(text("INSERT INTO user_key (user_id, public_key) VALUES (:user_id, :public_key)"), {"user_id": user_id, "public_key": public_key})
        db.session.commit()
        return jsonify({"ok": True, "already_registered": False})

    @app.get("/keys/<int:user_id>")
    def get_e2ee_identity_key(user_id):
        if not current_user_id():
            return jsonify({"error": "Authentication required"}), 401
        row = db.session.execute(text("SELECT public_key FROM user_key WHERE user_id = :user_id"), {"user_id": user_id}).scalar_one_or_none()
        return jsonify({"public_key": row or ""})

    if not getattr(app, "_prepza_e2ee_plaintext_guard", False):
        @app.before_request
        def _reject_plaintext_group_message_write():
            match = re.match(r"^/chats/(\d+)/messages$", request.path)
            if request.method != "POST" or not match:
                return None
            conversation_id = int(match.group(1))
            mode, _ = e2ee_state(conversation_id)
            if mode != "group_v1":
                return None
            payload = request.get_json(silent=True)
            if not isinstance(payload, dict):
                return jsonify({"error": "Encrypted group messages require a JSON payload"}), 400
            has_body = isinstance(payload.get("body"), str) and bool(payload.get("body").strip())
            has_attachment = payload.get("attachment_id") is not None
            if (has_body or has_attachment) and not isinstance(payload.get("nonce"), str):
                return jsonify({"error": "Plaintext group messages are disabled; encrypt on the client first"}), 409
            return None
        app._prepza_e2ee_plaintext_guard = True

    @app.post("/chats/<int:conversation_id>/enable-e2ee")
    @require_member
    def enable_group_e2ee(conversation, user_id):
        if not getattr(conversation, "is_group", False):
            return jsonify({"error": "Group E2EE can only be enabled for group conversations"}), 400
        if conversation.created_by != user_id:
            return jsonify({"error": "Only the group creator can enable E2EE"}), 403
        mode, epoch = e2ee_state(conversation.id)
        if mode == "group_v1":
            return jsonify({"ok": True, "e2ee_mode": mode, "key_epoch": epoch, "already_enabled": True})
        if mode != "legacy":
            return jsonify({"error": "Unsupported conversation encryption mode"}), 409
        # Existing groups are allowed to migrate. Their historical messages
        # remain legacy records; all new messages after the migration require
        # the group_v1 encrypted-message guard. This is necessary for accounts
        # and groups that existed before E2EE was introduced.
        missing_key_rows = db.session.execute(text("SELECT cp.user_id FROM conversation_participant cp LEFT JOIN user_key uk ON uk.user_id = cp.user_id WHERE cp.conversation_id = :conversation_id AND cp.left_at IS NULL AND uk.user_id IS NULL"), {"conversation_id": conversation.id}).all()
        if missing_key_rows:
            return jsonify({"error": "Every active group member must set up secure chat before E2EE can be enabled", "missing_user_ids": [int(row[0]) for row in missing_key_rows]}), 409
        db.session.execute(text("UPDATE conversation SET e2ee_mode = 'group_v1', key_epoch = 1 WHERE id = :conversation_id AND e2ee_mode = 'legacy'"), {"conversation_id": conversation.id})
        db.session.commit()
        return jsonify({"ok": True, "e2ee_mode": "group_v1", "key_epoch": 1, "already_enabled": False})

    @app.post("/chats/<int:conversation_id>/rotate-e2ee-key")
    @require_member
    def rotate_group_e2ee_key(conversation, user_id):
        if not getattr(conversation, "is_group", False):
            return jsonify({"error": "Key rotation is only used for group conversations"}), 400
        participant = participant_for(conversation.id, user_id)
        if not participant or (participant.role != "admin" and conversation.created_by != user_id):
            return jsonify({"error": "Only a group admin can rotate the E2EE key"}), 403
        mode, epoch = e2ee_state(conversation.id)
        if mode != "group_v1":
            return jsonify({"error": "Group E2EE is not enabled for this conversation"}), 409
        new_epoch = epoch + 1
        result = db.session.execute(text("UPDATE conversation SET key_epoch = :new_epoch WHERE id = :conversation_id AND e2ee_mode = 'group_v1' AND key_epoch = :old_epoch"), {"conversation_id": conversation.id, "old_epoch": epoch, "new_epoch": new_epoch})
        if result.rowcount != 1:
            db.session.rollback()
            return jsonify({"error": "Key epoch changed; retry with the current epoch"}), 409
        db.session.commit()
        return jsonify({"ok": True, "e2ee_mode": mode, "key_epoch": new_epoch})

    @app.get("/chats/<int:conversation_id>/key-envelopes")
    @require_member
    def get_group_key_envelopes(conversation, user_id):
        if not getattr(conversation, "is_group", False):
            return jsonify({"error": "Key envelopes are only used for group conversations"}), 400
        mode, epoch = e2ee_state(conversation.id)
        if mode != "group_v1":
            return jsonify({"conversation_id": conversation.id, "key_epoch": epoch, "e2ee_mode": mode, "envelopes": []})
        row = ConversationKeyEnvelope.query.filter_by(conversation_id=conversation.id, recipient_user_id=user_id, key_epoch=epoch).first()
        envelopes = [] if not row else [{"conversationId": row.conversation_id, "recipientUserId": row.recipient_user_id, "senderUserId": row.sender_user_id, "key_epoch": row.key_epoch, "nonce": row.nonce, "ciphertext": row.ciphertext, "version": row.version}]
        return jsonify({"conversation_id": conversation.id, "key_epoch": epoch, "e2ee_mode": mode, "envelopes": envelopes})

    @app.post("/chats/<int:conversation_id>/key-envelopes")
    @require_member
    def post_group_key_envelopes(conversation, user_id):
        if not getattr(conversation, "is_group", False):
            return jsonify({"error": "Key envelopes are only used for group conversations"}), 400
        mode, expected_epoch = e2ee_state(conversation.id)
        if mode != "group_v1":
            return jsonify({"error": "Group E2EE is not enabled for this conversation"}), 409
        locked_epoch = db.session.execute(text("SELECT key_epoch FROM conversation WHERE id = :conversation_id FOR UPDATE"), {"conversation_id": conversation.id}).scalar_one_or_none()\n        locked_epoch = int(locked_epoch or 0)\n        if locked_epoch != expected_epoch:\n            db.session.rollback()\n            return jsonify({"error": "Group key epoch changed; retry with the current epoch", "key_epoch": locked_epoch}), 409\n\n        provisioner = active_provisioner(conversation.id, expected_epoch)
        if provisioner is None or user_id != provisioner:
            return jsonify({"error": "Only the elected group key provisioner may publish the current epoch key", "provisioner_user_id": provisioner, "key_epoch": expected_epoch}), 403

        active_member_rows = db.session.execute(text("SELECT user_id FROM conversation_participant WHERE conversation_id = :conversation_id AND left_at IS NULL"), {"conversation_id": conversation.id}).all()
        active_member_ids = {int(row[0]) for row in active_member_rows if row[0] is not None}
        if not active_member_ids:
            return jsonify({"error": "The group has no active members"}), 409
        payload = request.get_json(silent=True) or {}
        envelopes = payload.get("envelopes")
        if not isinstance(envelopes, list) or not envelopes or len(envelopes) > 100:
            return jsonify({"error": "envelopes must contain 1-100 encrypted envelopes"}), 400
        if len(envelopes) != len(active_member_ids):
            return jsonify({"error": "A complete current-epoch key envelope is required for every active group member", "expected_member_count": len(active_member_ids)}), 409

        accepted = []
        seen_recipient_ids = set()
        for item in envelopes:
            if not isinstance(item, dict):
                return jsonify({"error": "Each envelope must be an object"}), 400
            try:
                recipient_id = int(item["recipient_user_id"])
                sender_id = int(item["sender_user_id"])
                epoch = int(item["key_epoch"])
                version = int(item["version"])
                nonce = str(item["nonce"])
                ciphertext = str(item["ciphertext"])
                conversation_id = int(item["conversation_id"])
            except (KeyError, TypeError, ValueError):
                return jsonify({"error": "Invalid encrypted envelope"}), 400
            if conversation_id != conversation.id or recipient_id in seen_recipient_ids:
                return jsonify({"error": "Envelope conversation or recipient is invalid"}), 400
            seen_recipient_ids.add(recipient_id)
            if sender_id != user_id or epoch != expected_epoch:
                return jsonify({"error": "Envelope sender or key epoch is invalid"}), 403
            if recipient_id not in active_member_ids or not participant_for(conversation.id, recipient_id):
                return jsonify({"error": "Envelope recipient is not an active member"}), 403
            if version != 1:
                return jsonify({"error": "Unsupported group key envelope version"}), 400
            if len(nonce) > 256 or len(ciphertext) > 20000:
                return jsonify({"error": "Encrypted envelope is too large"}), 400
            try:
                decode_base64(nonce, "nonce", max_bytes=12)
                decode_base64(ciphertext, "ciphertext", max_bytes=15000)\n                nonce_bytes = decode_base64(nonce, "nonce", max_bytes=12)\n                if len(nonce_bytes) != 12:\n                    raise ValueError("nonce must be exactly 12 bytes")
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
            accepted.append(ConversationKeyEnvelope(conversation_id=conversation.id, recipient_user_id=recipient_id, sender_user_id=sender_id, key_epoch=epoch, version=version, nonce=nonce, ciphertext=ciphertext))

        try:
            ConversationKeyEnvelope.query.filter_by(conversation_id=conversation.id, key_epoch=expected_epoch).delete(synchronize_session=False)
            db.session.add_all(accepted)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return jsonify({"error": "A duplicate group key envelope was detected; retry with the current epoch"}), 409
        return jsonify({"ok": True, "conversation_id": conversation.id, "key_epoch": expected_epoch, "stored": len(accepted)})
