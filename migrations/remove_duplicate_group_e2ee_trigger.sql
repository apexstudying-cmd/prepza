-- Keep a single authoritative conversation E2EE default trigger.
DROP TRIGGER IF EXISTS trg_prepza_default_new_group_e2ee ON conversation;
