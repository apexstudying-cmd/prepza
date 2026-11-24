"""Read-only base-chat routes, registered with explicit app-owned dependencies."""
from __future__ import annotations

from typing import Any, Callable

from flask import jsonify, request, session


def register_chat_read_routes(
    app: Any,
    *,
    Message: Any,
    chat_page_size: int,
    get_chat_or_404: Callable[[int, Any], Any],
    serialize_conversation_detail: Callable[[Any, Any], dict[str, Any]],
    serialize_chat_message: Callable[[Any], dict[str, Any]],
) -> None:
    """Register the existing conversation-detail and paginated-message routes."""

    @app.get("/chats/<int:conversation_id>")
    def get_chat(conversation_id):
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401
        conversation = get_chat_or_404(conversation_id, user_id)
        if not conversation:
            return jsonify({"error": "Conversation not found"}), 404
        return jsonify(serialize_conversation_detail(conversation, user_id))

    @app.get("/chats/<int:conversation_id>/messages")
    def list_chat_messages(conversation_id):
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Not logged in"}), 401
        conversation = get_chat_or_404(conversation_id, user_id)
        if not conversation:
            return jsonify({"error": "Conversation not found"}), 404
        query = Message.query.filter_by(conversation_id=conversation_id)
        before_id = request.args.get("before_id", type=int)
        if before_id:
            query = query.filter(Message.id < before_id)
        messages = (
            query.order_by(Message.created_at.desc(), Message.id.desc())
            .limit(chat_page_size)
            .all()
        )
        messages.reverse()
        return jsonify({"messages": [serialize_chat_message(message) for message in messages]})
