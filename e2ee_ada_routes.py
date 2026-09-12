"""Scoped Ada route for E2EE study chats.

The server receives plaintext only when a user explicitly selects study text
and asks Ada about it. It never loads conversation history, decrypts chat
messages, or accepts a local E2EE key from the client.
"""

import re

from flask import jsonify, request, session
from sqlalchemy import text

from ai_service import (
    AIRequest,
    AIBudgetExceededError,
    AIRateLimitExceededError,
    AIProviderError,
    check_daily_tutor_limit,
    get_monthly_ai_budget_usd,
    get_monthly_ai_spend_usd,
    is_spend_cap_reached,
    log_usage,
    route_and_generate,
)


MAX_SELECTED_TEXT = 20_000
MAX_PROMPT = 4_000
MAX_PAGE_SPAN = 50


def register_e2ee_ada_route(
    app,
    db,
    Conversation,
    ConversationParticipant,
    Document,
    User,
):
    """Register scoped Ada and the direct-chat plaintext guard."""
    if getattr(app, "_prepza_e2ee_ada_route_registered", False):
        return

    if not getattr(app, "_prepza_e2ee_direct_plaintext_guard", False):
        @app.before_request
        def _reject_plaintext_direct_message_write():
            match = re.match(r"^/chats/(\d+)/messages$", request.path)
            if request.method != "POST" or not match:
                return None

            conversation_id = int(match.group(1))
            state = db.session.execute(
                text("SELECT e2ee_mode FROM conversation WHERE id = :conversation_id"),
                {"conversation_id": conversation_id},
            ).scalar()
            if state != "direct_v1":
                return None

            payload = request.get_json(silent=True)
            if not isinstance(payload, dict):
                return jsonify({"error": "Encrypted direct messages require a JSON payload"}), 400

            has_body = isinstance(payload.get("body"), str) and bool(payload.get("body").strip())
            has_attachment = payload.get("attachment_id") is not None
            if (has_body or has_attachment) and not isinstance(payload.get("nonce"), str):
                return jsonify({"error": "Plaintext direct messages are disabled; encrypt on the client first"}), 409
            return None

        app._prepza_e2ee_direct_plaintext_guard = True

    def active_member(conversation_id, user_id):
        return ConversationParticipant.query.filter_by(
            conversation_id=conversation_id,
            user_id=user_id,
            left_at=None,
        ).first()

    def clean_text(value, maximum, field):
        if not isinstance(value, str):
            raise ValueError(f"{field} must be text")
        value = value.replace("\x00", "").strip()
        if not value:
            raise ValueError(f"{field} cannot be empty")
        if len(value) > maximum:
            raise ValueError(f"{field} exceeds the maximum allowed size")
        return value

    @app.post("/chats/<int:conversation_id>/ada/study")
    def scoped_ada_study(conversation_id):
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Authentication required"}), 401

        if not active_member(conversation_id, user_id):
            return jsonify({"error": "Conversation not found"}), 404

        conversation = db.session.get(Conversation, conversation_id)
        if not conversation:
            return jsonify({"error": "Conversation not found"}), 404

        state = db.session.execute(
            text("SELECT e2ee_mode, key_epoch FROM conversation WHERE id = :conversation_id"),
            {"conversation_id": conversation_id},
        ).mappings().first()
        if not state:
            return jsonify({"error": "Conversation encryption state is unavailable"}), 409

        e2ee_mode = state["e2ee_mode"] or "legacy"
        if e2ee_mode not in {"group_v1", "direct_v1"}:
            return jsonify({"error": "Scoped Ada requires an E2EE conversation"}), 409

        if e2ee_mode == "group_v1" and not conversation.is_group:
            return jsonify({"error": "Group E2EE state is inconsistent"}), 409
        if e2ee_mode == "direct_v1" and conversation.is_group:
            return jsonify({"error": "Direct E2EE state is inconsistent"}), 409

        current_key_epoch = int(state["key_epoch"] or 0)
        data = request.get_json(silent=True) or {}
        if data.get("context_scope") != "selected_document_pages":
            return jsonify({"error": "Ada accepts only selected document-page context"}), 400
        if data.get("explicit_user_context") is not True:
            return jsonify({"error": "Ada context must be explicitly selected by the user"}), 400

        try:
            document_id = int(data.get("document_id"))
            page_start = int(data.get("page_start"))
            page_end = int(data.get("page_end"))
            key_epoch = int(data.get("key_epoch"))
            selected_text = clean_text(data.get("selected_text"), MAX_SELECTED_TEXT, "selected_text")
            prompt = clean_text(data.get("prompt"), MAX_PROMPT, "prompt")
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid scoped Ada context"}), 400

        if document_id < 1 or page_start < 1 or page_end < page_start:
            return jsonify({"error": "Invalid document or page range"}), 400
        if page_end - page_start + 1 > MAX_PAGE_SPAN:
            return jsonify({"error": "Selected page range is too large"}), 400
        expected_epoch = current_key_epoch if e2ee_mode == "group_v1" else 1
        if key_epoch != expected_epoch:
            return jsonify({
                "error": "E2EE key epoch is stale; reopen the chat and retry",
                "key_epoch": expected_epoch,
            }), 409

        # The document is deliberately owner-scoped. A shared encrypted chat
        # document can later add an explicit ACL, but this endpoint must not
        # become a document-ID oracle in the meantime.
        document = db.session.get(Document, document_id)
        if not document or document.user_id != user_id or getattr(document, "is_removed", False):
            return jsonify({"error": "Study document not available"}), 404

        allowed, used, limit = check_daily_tutor_limit(user_id, plan_tier="free")
        if not allowed:
            return jsonify({
                "error": "Daily Ada limit reached",
                "used": used,
                "limit": limit,
            }), 429

        if is_spend_cap_reached():
            return jsonify({
                "error": "Fresh Ada generation is temporarily unavailable",
                "monthly_budget_usd": str(get_monthly_ai_budget_usd()),
                "monthly_spend_usd": str(get_monthly_ai_spend_usd()),
            }), 503

        system_prompt = (
            "You are Ada, Prepza's study tutor. The student has explicitly selected "
            "the study text below and asked a question about it. Answer only from "
            "the supplied context plus general academic knowledge. Do not claim "
            "to have access to the student's chat history, private documents, "
            "keys, or other pages. If the supplied excerpt is insufficient, say "
            "what is missing. Teach clearly, step by step when useful, and do not "
            "invent facts."
        )
        user_message = (
            f"Selected study context (pages {page_start}-{page_end}):\n\n"
            f"{selected_text}\n\n"
            f"Student question:\n{prompt}"
        )

        try:
            response = route_and_generate(AIRequest(
                task="TUTORING",
                system_prompt=system_prompt,
                user_message=user_message,
                cacheable_system=True,
            ))
        except AIBudgetExceededError:
            return jsonify({"error": "Fresh Ada generation is temporarily unavailable"}), 503
        except AIRateLimitExceededError:
            return jsonify({"error": "Daily Ada limit reached"}), 429
        except AIProviderError:
            return jsonify({"error": "Ada could not answer right now"}), 502

        log_usage(
            user_id,
            request_type="tutor_message",
            model=response.model_used,
            provider=response.provider,
            usage=response.usage,
        )

        return jsonify({
            "answer": response.text,
            "model_used": response.model_used,
            "key_epoch": expected_epoch,
            "context_scope": "selected_document_pages",
        }), 200

    app._prepza_e2ee_ada_route_registered = True
