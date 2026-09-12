-- Harden the E2EE state machine at the database boundary.
-- Repeat-safe: each constraint is created only when it is absent.
-- Existing legacy/direct conversations are not converted by this migration.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_conversation_e2ee_mode_supported'
          AND conrelid = 'conversation'::regclass
    ) THEN
        ALTER TABLE conversation
            ADD CONSTRAINT ck_conversation_e2ee_mode_supported
            CHECK (e2ee_mode IN ('legacy', 'direct_v1', 'group_v1'));
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_conversation_key_epoch_nonnegative'
          AND conrelid = 'conversation'::regclass
    ) THEN
        ALTER TABLE conversation
            ADD CONSTRAINT ck_conversation_key_epoch_nonnegative
            CHECK (key_epoch >= 0);
    END IF;
END $$;

-- A group_v1 conversation must always have a positive current epoch.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_conversation_group_e2ee_epoch'
          AND conrelid = 'conversation'::regclass
    ) THEN
        ALTER TABLE conversation
            ADD CONSTRAINT ck_conversation_group_e2ee_epoch
            CHECK (e2ee_mode <> 'group_v1' OR key_epoch >= 1);
    END IF;
END $$;
