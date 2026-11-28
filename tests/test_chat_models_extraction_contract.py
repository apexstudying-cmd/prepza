from __future__ import annotations

from pathlib import Path

from chat_models import Conversation, ConversationParticipant, Message, MessageAttachment

ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")


def test_chat_models_are_module_owned_and_reexported_from_legacy_app() -> None:
    assert "from chat_models import Conversation, ConversationParticipant, Message, MessageAttachment" in APP_SOURCE
    for name in ("Conversation", "ConversationParticipant", "Message", "MessageAttachment"):
        assert f"class {name}(db.Model)" not in APP_SOURCE


def test_chat_model_table_and_column_contracts_are_preserved() -> None:
    expected = (
        (Conversation, "conversation", {"id", "is_group", "name", "created_by", "created_at", "updated_at", "status", "e2ee_mode", "key_epoch"}),
        (ConversationParticipant, "conversation_participant", {"id", "conversation_id", "user_id", "role", "joined_at", "last_read_at", "left_at", "muted"}),
        (Message, "message", {"id", "conversation_id", "sender_id", "body", "nonce", "is_deleted", "created_at", "edited_at", "e2ee_key_epoch"}),
        (MessageAttachment, "message_attachment", {"id", "conversation_id", "message_id", "uploaded_by_user_id", "source_document_content_id", "storage_path", "file_type", "original_filename", "file_size_bytes", "status", "created_at", "cached_view_url", "cached_view_url_expires_at"}),
    )
    for model, table, columns in expected:
        assert model.__tablename__ == table
        assert set(model.__table__.columns.keys()) == columns


def test_chat_e2ee_and_attachment_integrity_constraints_are_preserved() -> None:
    assert Conversation.__table__.c.e2ee_mode.default.arg == "legacy"
    assert Conversation.__table__.c.key_epoch.default.arg == 0
    assert Message.__table__.c.e2ee_key_epoch.default.arg == 0
    assert ConversationParticipant.__table__.constraints
    unique = [
        constraint for constraint in ConversationParticipant.__table__.constraints
        if getattr(constraint, "name", None) == "uq_participant_conversation_user"
    ]
    assert len(unique) == 1
    attachment_targets = {
        foreign_key.target_fullname
        for column in MessageAttachment.__table__.columns
        for foreign_key in column.foreign_keys
    }
    assert {"conversation.id", "message.id", "user.id", "document_content.id"} <= attachment_targets
