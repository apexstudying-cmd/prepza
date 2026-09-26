-- Track the student's document study history without creating a separate
-- event row for every page heartbeat. The document remains the canonical
-- reference; last_opened_at powers Recent/History ordering.
ALTER TABLE document
  ADD COLUMN IF NOT EXISTS last_opened_at TIMESTAMP NULL;

CREATE INDEX IF NOT EXISTS ix_document_user_last_opened
  ON document (user_id, last_opened_at DESC, id DESC);
