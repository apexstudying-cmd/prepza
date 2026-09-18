-- O4 offline chat reliability: stable client IDs prevent duplicate messages
-- when a reconnect retry occurs after the server committed the first request
-- but the client lost the response. Safe to run repeatedly on PostgreSQL.

CREATE TABLE IF NOT EXISTS chat_message_idempotency (
    conversation_id INTEGER NOT NULL,
    sender_id INTEGER NOT NULL,
    client_message_id VARCHAR(128) NOT NULL,
    message_id INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (conversation_id, sender_id, client_message_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_chat_message_idempotency_message
    ON chat_message_idempotency (message_id);
