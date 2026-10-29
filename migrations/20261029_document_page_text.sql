-- Persist extraction output per source page for citations and retrieval.
-- Existing combined extracted_text remains the compatibility source for current
-- generation routes; new retrieval code reads this table only after access checks.
CREATE TABLE IF NOT EXISTS document_page_text (
    id BIGSERIAL PRIMARY KEY,
    document_content_id INTEGER NOT NULL REFERENCES document_content(id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL CHECK (page_number > 0),
    page_text TEXT NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    source_version VARCHAR(64) NOT NULL,
    extractor_version VARCHAR(50) NOT NULL,
    extracted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_document_page_text_content_page UNIQUE (document_content_id, page_number)
);

CREATE INDEX IF NOT EXISTS ix_document_page_text_source_version
    ON document_page_text (document_content_id, source_version);
