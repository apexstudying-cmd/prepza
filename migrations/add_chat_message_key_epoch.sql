-- Persist the group E2EE epoch used for each encrypted message/edit.
-- Nullable keeps legacy/direct messages compatible. Safe to run repeatedly.
ALTER TABLE message ADD COLUMN IF NOT EXISTS key_epoch INTEGER;
CREATE INDEX IF NOT EXISTS ix_message_conversation_key_epoch
    ON message (conversation_id, key_epoch);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_message_key_epoch_positive'
          AND conrelid = 'message'::regclass
    ) THEN
        ALTER TABLE message
            ADD CONSTRAINT ck_message_key_epoch_positive
            CHECK (key_epoch IS NULL OR key_epoch >= 1);
    END IF;
END $$;
