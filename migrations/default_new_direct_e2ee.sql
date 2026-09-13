-- Make new 1:1 conversations E2EE by default.
-- Existing conversations are intentionally untouched; the rollout migration
-- already classified existing direct chats as direct_v1.

CREATE OR REPLACE FUNCTION prepza_default_new_conversation_e2ee() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.is_group = TRUE THEN
        NEW.e2ee_mode := 'group_v1';
        NEW.key_epoch := 1;
    ELSE
        NEW.e2ee_mode := 'direct_v1';
        NEW.key_epoch := 0;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_prepza_default_new_conversation_e2ee ON conversation;
CREATE TRIGGER trg_prepza_default_new_conversation_e2ee
BEFORE INSERT ON conversation
FOR EACH ROW
EXECUTE FUNCTION prepza_default_new_conversation_e2ee();
