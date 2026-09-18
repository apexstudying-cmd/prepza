"""Server-side metadata support for the WhatsApp-style study chat.

Message bodies remain opaque/E2EE. This module stores only non-content
metadata needed by the chat UX: message kind and server-computed read
receipt counts. Reply targets and reaction payloads stay inside the
encrypted message body.

The project currently has no migration framework, so the additive metadata
table is created idempotently at startup; the matching SQL migration is
also kept in the repository for explicit database provisioning.
"""
import json
from datetime import datetime
from threading import Lock

from flask import request, session
from sqlalchemy import text

from app import app, db, ConversationParticipant

_SCHEMA_LOCK = Lock()
_SCHEMA_READY = False


def ensure_chat_metadata_schema():
    """Create the additive chat metadata table if it is missing."""
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return
        try:
            with app.app_context():
                db.session.execute(text("""
                    CREATE TABLE IF NOT EXISTS chat_message_meta (
                        message_id INTEGER PRIMARY KEY,
                        conversation_id INTEGER NOT NULL,
                        kind VARCHAR(20) NOT NULL DEFAULT 'text',
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                db.session.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_chat_message_meta_conversation_kind
                    ON chat_message_meta (conversation_id, kind)
                """))
                db.session.execute(text("""
                    ALTER TABLE "user"
                    ADD COLUMN IF NOT EXISTS read_receipts_enabled BOOLEAN NOT NULL DEFAULT TRUE
                """))
                db.session.commit()
            _SCHEMA_READY = True
        except Exception:
            db.session.rollback()
            app.logger.exception("Could not initialize chat metadata schema")


def _message_kind_map(message_ids):
    if not message_ids:
        return {}
    ensure_chat_metadata_schema()
    placeholders = ",".join(f":id_{i}" for i in range(len(message_ids)))
    params = {f"id_{i}": message_id for i, message_id in enumerate(message_ids)}
    rows = db.session.execute(
        text(f"SELECT message_id, kind FROM chat_message_meta WHERE message_id IN ({placeholders})"),
        params,
    ).fetchall()
    return {int(row[0]): str(row[1]) for row in rows}


def _reaction_unread_count(conversation_id, user_id, last_read_at):
    ensure_chat_metadata_schema()
    params = {"conversation_id": conversation_id, "user_id": user_id}
    sql = """
        SELECT COUNT(*)
        FROM message AS m
        JOIN chat_message_meta AS meta ON meta.message_id = m.id
        WHERE m.conversation_id = :conversation_id
          AND m.sender_id != :user_id
          AND meta.kind = 'reaction'
    """
    if last_read_at:
        sql += " AND m.created_at > :last_read_at"
        params["last_read_at"] = last_read_at
    return int(db.session.execute(text(sql), params).scalar() or 0)


def _conversation_id_from_path():
    parts = request.path.strip("/").split("/")
    if len(parts) >= 2 and parts[0] == "chats":
        try:
            return int(parts[1])
        except (TypeError, ValueError):
            return None
    return None


def _decorate_message_list(response):
    payload = response.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get("messages"), list):
        return response
    user_id = session.get("user_id")
    conversation_id = _conversation_id_from_path()
    if not user_id or conversation_id is None:
        return response

    messages = payload["messages"]
    ids = [m.get("id") for m in messages if isinstance(m, dict) and isinstance(m.get("id"), int)]
    kinds = _message_kind_map(ids)
    participants = ConversationParticipant.query.filter_by(
        conversation_id=conversation_id, left_at=None
    ).all()
    other_participants = [p for p in participants if p.user_id != user_id]

    decorated = []
    for item in messages:
        if not isinstance(item, dict):
            decorated.append(item)
            continue
        next_item = dict(item)
        message_id = item.get("id")
        kind = kinds.get(message_id, "text")
        next_item["kind"] = kind
        if isinstance(message_id, int) and item.get("sender_id") == user_id and other_participants:
            created_raw = item.get("created_at")
            read_by_count = 0
            if created_raw:
                try:
                    created_at = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
                    for participant in other_participants:
                        last_read = participant.last_read_at
                        if last_read is None:
                            continue
                        if last_read.tzinfo is None:
                            last_read_cmp = last_read
                            created_cmp = created_at.replace(tzinfo=None)
                        else:
                            last_read_cmp = last_read
                            created_cmp = created_at
                        if last_read_cmp >= created_cmp:
                            read_by_count += 1
                except (TypeError, ValueError):
                    pass
            next_item["read_by_count"] = read_by_count
            next_item["read_by_all"] = read_by_count == len(other_participants)
        decorated.append(next_item)

    payload["messages"] = decorated
    response.set_data(json.dumps(payload))
    response.headers["Content-Type"] = "application/json"
    return response


@app.before_request
def _chat_metadata_before_request():
    ensure_chat_metadata_schema()


@app.after_request
def _chat_metadata_after_request(response):
    path = request.path

    if request.method == "POST" and path.startswith("/chats/") and path.endswith("/messages"):
        if 200 <= response.status_code < 300:
            try:
                conversation_id = _conversation_id_from_path()
                request_payload = request.get_json(silent=True) or {}
                response_payload = response.get_json(silent=True) or {}
                message = response_payload.get("message") if isinstance(response_payload, dict) else None
                if isinstance(response_payload, dict) and message is None and "id" in response_payload:
                    message = response_payload
                message_id = message.get("id") if isinstance(message, dict) else None
                kind = request_payload.get("kind", "text")
                if kind not in {"text", "reaction"}:
                    kind = "text"
                if conversation_id and isinstance(message_id, int):
                    ensure_chat_metadata_schema()
                    db.session.execute(
                        text("""
                            INSERT INTO chat_message_meta (message_id, conversation_id, kind)
                            VALUES (:message_id, :conversation_id, :kind)
                            ON CONFLICT(message_id) DO UPDATE SET kind = excluded.kind
                        """),
                        {"message_id": message_id, "conversation_id": conversation_id, "kind": kind},
                    )
                    db.session.commit()
                    if isinstance(message, dict):
                        enriched = dict(message)
                        enriched["kind"] = kind
                        response_payload["message"] = enriched
                        response.set_data(json.dumps(response_payload))
                        response.headers["Content-Type"] = "application/json"
            except Exception:
                db.session.rollback()
                app.logger.exception("Could not persist chat message metadata")
        return response

    if request.method == "GET" and path.startswith("/chats/") and path.endswith("/messages"):
        try:
            return _decorate_message_list(response)
        except Exception:
            db.session.rollback()
            app.logger.exception("Could not decorate chat message metadata")
            return response

    if request.method == "GET" and path == "/chats":
        payload = response.get_json(silent=True)
        if not isinstance(payload, dict) or not isinstance(payload.get("chats"), list):
            return response
        try:
            ensure_chat_metadata_schema()
            viewer_id = session.get("user_id")
            for chat in payload["chats"]:
                if not isinstance(chat, dict) or not isinstance(chat.get("id"), int) or not viewer_id:
                    continue
                participant = ConversationParticipant.query.filter_by(
                    conversation_id=chat["id"], user_id=viewer_id, left_at=None
                ).first()
                if participant is None:
                    continue
                reaction_unread = _reaction_unread_count(
                    chat["id"], viewer_id, participant.last_read_at
                )
                chat["unread_count"] = max(0, int(chat.get("unread_count") or 0) - reaction_unread)
                if chat.get("last_message_at"):
                    chat["last_message"] = "Encrypted message"
            response.set_data(json.dumps(payload))
            response.headers["Content-Type"] = "application/json"
        except Exception:
            db.session.rollback()
            app.logger.exception("Could not decorate chat list metadata")
        return response

    return response


ensure_chat_metadata_schema()
