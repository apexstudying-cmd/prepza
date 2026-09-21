-- Scope student-facing AI generation jobs to their owner.
-- Legacy text-extraction jobs may remain NULL; all new generation jobs set user_id.
ALTER TABLE ai_job
  ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES "user"(id);

CREATE INDEX IF NOT EXISTS ix_ai_job_user_id
  ON ai_job (user_id);

CREATE INDEX IF NOT EXISTS ix_ai_job_user_document_feature
  ON ai_job (user_id, document_content_id, feature, id DESC);
