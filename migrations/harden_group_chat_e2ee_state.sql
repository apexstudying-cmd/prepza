-- Harden the E2EE state machine at the database boundary.
-- This migration is intentionally repeat-safe and does not alter existing
-- legacy/direct conversations into group E2EE.

ALTER TABLE conversation
    ADD CONSTRAINT ck_conversation_e2ee_mode_supported
    CHECK (e2ee_mode IN ('legacy', 'direct_v1', 'group_v1'));

ALTER TABLE conversation
    ADD CONSTRAINT ck_conversation_key_epoch_nonnegative
    CHECK (key_epoch >= 0);

-- A group_v1 conversation must always have a positive current epoch.
ALTER TABLE conversation
    ADD CONSTRAINT ck_conversation_group_e2ee_epoch
    CHECK (e2ee_mode <> 'group_v1' OR key_epoch >= 1);
