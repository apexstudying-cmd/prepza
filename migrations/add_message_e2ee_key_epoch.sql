-- Store the group-key epoch used for each chat message.
-- This is required to decrypt historical messages after membership-driven
-- key rotation without exposing old keys to newly removed members.
ALTER TABLE message
    ADD COLUMN IF NOT EXISTS e2ee_key_epoch INTEGER NOT NULL DEFAULT 0;

ALTER TABLE message
    ADD CONSTRAINT ck_message_e2ee_key_epoch_nonnegative
    CHECK (e2ee_key_epoch >= 0);

CREATE INDEX IF NOT EXISTS ix_message_conversation_e2ee_epoch
    ON message (conversation_id, e2ee_key_epoch, created_at);
