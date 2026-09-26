-- Study Hub chat shares reference the already-existing source DocumentContent.
-- AI-generated artifacts are deliberately excluded from this relationship.
ALTER TABLE message_attachment
  ADD COLUMN IF NOT EXISTS source_document_content_id INTEGER
  REFERENCES document_content(id);
CREATE INDEX IF NOT EXISTS ix_message_attachment_source_document_content
  ON message_attachment(source_document_content_id);
