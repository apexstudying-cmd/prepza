-- New groups must not enter group_v1 before their client-side key envelopes exist.
-- E2EE is enabled explicitly by /chats/<id>/enable-e2ee after every active
-- member has registered a public identity key.
CREATE OR REPLACE FUNCTION prepza_default_new_group_e2ee() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.is_group = TRUE THEN
        NEW.e2ee_mode := 'legacy';
        NEW.key_epoch := 0;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_prepza_default_new_group_e2ee ON conversation;
CREATE TRIGGER trg_prepza_default_new_group_e2ee
BEFORE INSERT ON conversation
FOR EACH ROW EXECUTE FUNCTION prepza_default_new_group_e2ee();
