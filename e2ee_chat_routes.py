"""E2EE group-chat HTTP routes.

This module deliberately keeps all group-key material opaque to the server.
Only encrypted envelopes are accepted/stored. The route registration function
is called after the application's Conversation/User models are defined.
"""

from functools import wraps

from flask import jsonify, request, session
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

    @app.get("/chats/<int:conversation_id>/key-envelopes")
    @require_member
    def get_group_key_envelopes(conversation, user_id):
        if not getattr(conversation, "is_group", False):
            return jsonify({"error": "Key envelopes are only used for group conversations"}), 400
        if getattr(conversation, "e2ee_mode", "legacy") != "group_v1":
            return jsonify({
                "conversation_id": conversation.id,
                "key_epoch": getattr(conversation, "key_epoch", 0),
                "e2ee_mode": getattr(conversation, "e2ee_mode", "legacy"),
                "envelopes": [],
            })

        row = ConversationKeyEnvelope.query.filter_by(
            conversation_id=conversation.id,
            recipient_user_id=user_id,
            key_epoch=conversation.key_epoch,
        ).first()
        envelopes = [] if not row else [{
            "conversationId": row.conversation_id,
            "recipientUserId": row.recipient_user_id,
            "senderUserId": row.sender_user_id,
            "key_epoch": row.key_epoch,
            "nonce": row.nonce,
            "ciphertext": row.ciphertext,
            "version": row.version,
        }]
        return jsonify({
            "conversation_id": conversation.id,
            "key_epoch": conversation.key_epoch,
            "e2ee_mode": conversation.e2ee_mode,
            "envelopes": envelopes,
        })

    @app.post("/chats/<int:conversation_id>/key-envelopes")
    @require_member
    def post_group_key_envelopes(conversation, user_id):
        if not getattr(conversation, "is_group", False):
            return jsonify({"error": "Key envelopes are only used for group conversations"}), 400
        if getattr(conversation, "e2ee_mode", "legacy") != "group_v1":
            return jsonify({"error": "Group E2EE is not enabled for this conversation"}), 409

        payload = request.get_json(silent=True) or {}
        envelopes = payload.get("envelopes")
        if not isinstance(envelopes, list) or not envelopes or len(envelopes) > 100:
            return jsonify({"error": "envelopes must contain 1-100 encrypted envelopes"}), 400

        expected_epoch = conversation.key_epoch
        accepted = []
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
            except (KeyError, TypeError, ValueError):
                return jsonify({"error": "Invalid encrypted envelope"}), 400

            # The uploader must be a current member and may only provision the
            # current epoch. This prevents stale/future-key writes.
            if sender_id != user_id or epoch != expected_epoch:
                return jsonify({"error": "Envelope sender or key epoch is invalid"}), 403
            if not participant_for(conversation.id, recipient_id):
                return jsonify({"error": "Envelope recipient is not an active member"}), 403
            if version != 1 or not nonce or not ciphertext:
                return jsonify({"error": "Unsupported or incomplete envelope"}), 400
            if len(nonce) > 64 or len(ciphertext) > 10000:
                return jsonify({"error": "Encrypted envelope is too large"}), 400

            accepted.append({
                "conversation_id": conversation.id,
                "recipient_user_id": recipient_id,
                "sender_user_id": sender_id,
                "key_epoch": epoch,
                "version": version,
                "nonce": nonce,
                "ciphertext": ciphertext,
            })

        for values in accepted:
            existing = ConversationKeyEnvelope.query.filter_by(
                conversation_id=values["conversation_id"],
                recipient_user_id=values["recipient_user_id"],
                key_epoch=values["key_epoch"],
            ).first()
            if existing:
                if existing.sender_user_id != values["sender_user_id"]:
                    return jsonify({"error": "Key envelope already belongs to another sender"}), 409
                existing.version = values["version"]
                existing.nonce = values["nonce"]
                existing.ciphertext = values["ciphertext"]
            else:
                db.session.add(ConversationKeyEnvelope(**values))

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return jsonify({"error": "Envelope conflict; retry with the current key epoch"}), 409

        return jsonify({"ok": True, "stored": len(accepted), "key_epoch": expected_epoch})
