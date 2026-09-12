-- Prepza group-chat E2EE foundation
--
-- The server stores only encrypted key envelopes. It never stores a
-- plaintext group conversation key. A future membership-change migration
-- will advance key_epoch and require a fresh key for the remaining members.

ALTER TABLE conversation
    ADD COLUMN IF NOT EXISTS e2ee_mode VARCHAR(20) NOT NULL DEFAULT 'legacy';

ALTER TABLE conversation
    ADD COLUMN IF NOT EXISTS key_epoch INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS conversation_key_envelope (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES conversation(id) ON DELETE CASCADE,
    recipient_user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    sender_user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    key_epoch INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 1,
    nonce VARCHAR(64) NOT NULL,
    ciphertext TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_conversation_key_envelope_recipient_epoch
        UNIQUE (conversation_id, recipient_user_id, key_epoch),
    CONSTRAINT ck_conversation_key_envelope_epoch_nonnegative
        CHECK (key_epoch >= 0),
    CONSTRAINT ck_conversation_key_envelope_version_positive
        CHECK (version > 0)
);

CREATE INDEX IF NOT EXISTS ix_conversation_key_envelope_conversation
    ON conversation_key_envelope (conversation_id, key_epoch);

CREATE INDEX IF NOT EXISTS ix_conversation_key_envelope_recipient
    ON conversation_key_envelope (recipient_user_id, conversation_id, key_epoch);

-- Existing 1:1 encrypted chats are already using client-side AES-GCM.
-- New group conversations should opt into the explicit group-key envelope
-- protocol once the frontend wiring lands.
UPDATE conversation
SET e2ee_mode = CASE WHEN is_group = TRUE THEN 'group_v1' ELSE 'direct_v1' END
WHERE e2ee_mode = 'legacy';
