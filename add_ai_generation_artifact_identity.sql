-- Shared identity/state for reusable AI-generated artifacts.
--
-- The fingerprint is the concurrency boundary: one fingerprint may have
-- exactly one generation in flight, regardless of which student triggered it.
-- GeneratedMaterial remains the document/user-facing attachment; this table
-- owns the reusable artifact identity and payload.

CREATE TABLE IF NOT EXISTS ai_generation_artifact (
    id BIGSERIAL PRIMARY KEY,
    fingerprint VARCHAR(64) NOT NULL,
    content_hash VARCHAR(128) NOT NULL,
    feature VARCHAR(100) NOT NULL,
    parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
    prompt_version VARCHAR(100) NOT NULL,
    schema_version VARCHAR(100) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'generating',
    payload JSONB,
    error_message TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITHOUT TIME ZONE,
    CONSTRAINT uq_ai_generation_artifact_fingerprint UNIQUE (fingerprint),
    CONSTRAINT ck_ai_generation_artifact_status
        CHECK (status IN ('generating', 'ready', 'failed'))
);

CREATE INDEX IF NOT EXISTS ix_ai_generation_artifact_content_feature
    ON ai_generation_artifact (content_hash, feature);

-- Idempotent migration safety: the table and indexes above can be applied
-- repeatedly while deploying the generation-path integration.
