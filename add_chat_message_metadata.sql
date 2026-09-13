-- Chunk 2: additive metadata for WhatsApp-style chat interactions.
-- Safe to run repeatedly. Message bodies remain E2EE ciphertext; this
-- table stores only whether a message is a normal message or a reaction
-- event. Reply targets and reaction emoji/action stay inside ciphertext.

CREATE TABLE IF NOT EXISTS chat_message_meta (
    message_id INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL,
    kind VARCHAR(20) NOT NULL DEFAULT 'text',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_chat_message_meta_kind CHECK (kind IN ('text', 'reaction'))
);

CREATE INDEX IF NOT EXISTS ix_chat_message_meta_conversation_kind
    ON chat_message_meta (conversation_id, kind);
