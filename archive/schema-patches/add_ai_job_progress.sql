-- Adds durable progress state for user-visible AI generation tracking.
ALTER TABLE ai_job
ADD COLUMN IF NOT EXISTS progress_percent INTEGER NOT NULL DEFAULT 0;
ALTER TABLE ai_job
ADD COLUMN IF NOT EXISTS progress_stage VARCHAR(80);
