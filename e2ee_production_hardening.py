"""Production hardening for the browser E2EE chat bootstrap path.

This module is additive: it does not replace the existing E2EE routes. It
provides an unambiguous public-key lookup endpoint and makes group creation
fail before a conversation row is created when an active member has no
registered encryption identity.
"""

import re

from flask import jsonify, request, session
from sqlalchemy import text


def register_e2ee_production_hardening(app, db, Conversation, ConversationParticipant):
    if getattr(app, "_prepza_e2ee_production_hardening", False):
        return

    @app.get("/e2ee/keys/<int:user_id>")
    def get_e2ee_public_key_for_chat(user_id):
        if not session.get("user_id"):
            return jsonify({"error": "Authentication required"}), 401
        row = db.session.execute(
            text("SELECT public_key FROM user_key WHERE user_id = :user_id"),
            {"user_id": user_id},
        ).scalar_one_or_none()
        return jsonify({
            "public_key": row or "",
            "secure_chat_ready": bool(row),
        })

    @app.before_request
    def reject_unready_e2ee_group_creation():
        if request.method != "POST":
            return None

        # Initial group creation must be atomic with respect to E2EE readiness.
        if request.path == "/chats":
            payload = request.get_json(silent=True) or {}
            if not isinstance(payload, dict) or not payload.get("is_group"):
                return None
            raw_ids = payload.get("participant_ids") or []
            try:
                requested_ids = {int(value) for value in raw_ids}
                creator_id = int(session.get("user_id"))
            except (TypeError, ValueError):
                return jsonify({"error": "Invalid group participant list"}), 400
            requested_ids.add(creator_id)
            if not requested_ids:
                return None
            rows = db.session.execute(
                text(
                    "SELECT cp.user_id FROM conversation_participant cp "
                    "WHERE 1 = 0"
                )
            )
            # The query above intentionally does not depend on an existing
            # conversation; use the user_key table directly for this preflight.
            existing_key_rows = db.session.execute(
                text("SELECT user_id FROM user_key WHERE user_id = ANY(:ids)"),
                {"ids": list(requested_ids)},
            ).all()
            ready_ids = {int(row[0]) for row in existing_key_rows}
            missing_ids = sorted(requested_ids - ready_ids)
            if missing_ids:
                return jsonify({
                    "error": "Every group member must complete secure chat setup before the group can be created",
                    "code": "GROUP_E2EE_MEMBERS_NOT_READY",
                    "missing_user_ids": missing_ids,
                }), 409
            return None

        # Membership additions must also be E2EE-ready because adding a member
        # advances the group epoch and requires a complete encrypted envelope
        # set for the new epoch.
        match = re.fullmatch(r"/chats/(\d+)/members", request.path)
        if not match:
            return None
        conversation_id = int(match.group(1))
        conversation = db.session.get(Conversation, conversation_id)
        if not conversation or not conversation.is_group:
            return None
        requester_id = session.get("user_id")
        if not requester_id:
            return None
        participant = ConversationParticipant.query.filter_by(
            conversation_id=conversation_id,
            user_id=requester_id,
            left_at=None,
        ).first()
        if not participant or participant.role != "admin":
            return None
        payload = request.get_json(silent=True) or {}
        raw_ids = payload.get("user_ids") or []
        try:
            requested_ids = {int(value) for value in raw_ids}
        except (TypeError, ValueError):
            return None
        if not requested_ids:
            return None
        existing_key_rows = db.session.execute(
            text("SELECT user_id FROM user_key WHERE user_id = ANY(:ids)"),
            {"ids": list(requested_ids)},
        ).all()
        ready_ids = {int(row[0]) for row in existing_key_rows}
        missing_ids = sorted(requested_ids - ready_ids)
        if missing_ids:
            return jsonify({
                "error": "Every new group member must complete secure chat setup before being added",
                "code": "GROUP_E2EE_MEMBERS_NOT_READY",
                "missing_user_ids": missing_ids,
            }), 409
        return None

    app._prepza_e2ee_production_hardening = True
