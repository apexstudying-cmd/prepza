-- AI artifact reuse foundation.
--
-- GeneratedMaterial currently has one row per (document_content_id,
-- material_type), which is too coarse for parameterized generations such as
-- different podcast lengths or flashcard counts. This table is deliberately
-- separate so the existing artifact rows remain backward-compatible while
-- the new fingerprinted cache is introduced incrementally.

CREATE TABLE IF NOT EXISTS ai_artifact_cache (
    id SERIAL PRIMARY KEY,
    generation_fingerprint VARCHAR(128) NOT NULL UNIQUE,
    document_content_id INTEGER NOT NULL REFERENCES document_content(id),
    material_type VARCHAR(30) NOT NULL,
    scope VARCHAR(20) NOT NULL DEFAULT 'shared',
    owner_user_id INTEGER NULL REFERENCES "user"(id),
    parameters_json TEXT NULL,
    generation_version VARCHAR(50) NOT NULL DEFAULT 'v1',
    status VARCHAR(20) NOT NULL DEFAULT 'generating',
    payload TEXT NULL,
    model_used VARCHAR(100) NULL,
    provider VARCHAR(50) NULL,
    error_message VARCHAR(500) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP NULL
);

CREATE INDEX IF NOT EXISTS ix_ai_artifact_cache_document_type
    ON ai_artifact_cache (document_content_id, material_type);

CREATE INDEX IF NOT EXISTS ix_ai_artifact_cache_owner
    ON ai_artifact_cache (owner_user_id);

-- One shared artifact may exist for a fingerprint, while private artifacts
-- are explicitly scoped to an owner. The fingerprint remains the primary
-- concurrency/idempotency key.
