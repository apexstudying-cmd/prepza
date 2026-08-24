-- Chunk 3 (AI pipeline) schema additions. Run in Supabase SQL editor.

-- ai_usage_log currently tracks `model` but not which provider served
-- it. Only Anthropic exists today, but this keeps ai_service.py's
-- logging honest as soon as a second provider is added, without a
-- second migration.
ALTER TABLE ai_usage_log ADD COLUMN IF NOT EXISTS provider VARCHAR(20);

-- Configurable monthly AI spend cap, same pattern as price_notes /
-- price_past_paper / price_qna. ai_service.py defaults to $20 if this
-- row is missing, so this insert is just making it explicit/editable
-- from the admin settings UI later.
INSERT INTO system_setting (key, value)
VALUES ('ai_monthly_budget_usd', '20.00')
ON CONFLICT (key) DO NOTHING;

-- Sanity check - confirm both landed.
SELECT column_name FROM information_schema.columns
WHERE table_name = 'ai_usage_log' AND column_name = 'provider';

SELECT key, value FROM system_setting WHERE key = 'ai_monthly_budget_usd';
