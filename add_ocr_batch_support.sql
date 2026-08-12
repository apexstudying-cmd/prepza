-- Adds support for routing OCR page-transcription through the Anthropic
-- Message Batches API (50% cheaper than synchronous calls) instead of
-- one synchronous call per scanned page.

-- Lets an admin look up the underlying Anthropic batch directly in the
-- Anthropic Console if a document ever seems stuck in "processing".
ALTER TABLE ai_job ADD COLUMN IF NOT EXISTS batch_id VARCHAR(100);

-- Minimum number of scanned/OCR-needed pages a single document must
-- have before its transcription is routed through the Batch API rather
-- than the existing fast synchronous per-page path. Below this, the
-- coordination/latency overhead of a batch isn't worth it. Configurable
-- without a redeploy - just UPDATE this row's value.
INSERT INTO system_setting (key, value)
VALUES ('ocr_batch_page_threshold', '3')
ON CONFLICT (key) DO NOTHING;
