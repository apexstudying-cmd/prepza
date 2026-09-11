-- Shared/private identity and state for reusable AI-generated artifacts.
--
-- The fingerprint is the concurrency boundary: one fingerprint may have
-- exactly one generation in flight. Shared artifacts may be reused across
-- students; private artifacts are isolated by owner_user_id.
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
    scope VARCHAR(20) NOT NULL DEFAULT 'shared',
    owner_user_id BIGINT,
    status VARCHAR(30) NOT NULL DEFAULT 'generating',
    payload JSONB,
    error_message TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITHOUT TIME ZONE,
    CONSTRAINT uq_ai_generation_artifact_fingerprint UNIQUE (fingerprint),
    CONSTRAINT ck_ai_generation_artifact_status
        CHECK (status IN ('generating', 'ready', 'failed')),
    CONSTRAINT ck_ai_generation_artifact_scope
        CHECK (scope IN ('shared', 'private')),
    CONSTRAINT ck_ai_generation_artifact_private_owner
        CHECK ((scope = 'shared' AND owner_user_id IS NULL)
            OR (scope = 'private' AND owner_user_id IS NOT NULL))
);

-- Idempotent upgrades for databases where the original table already exists.
ALTER TABLE ai_generation_artifact
    ADD COLUMN IF NOT EXISTS scope VARCHAR(20) NOT NULL DEFAULT 'shared';

ALTER TABLE ai_generation_artifact
    ADD COLUMN IF NOT EXISTS owner_user_id BIGINT;

CREATE INDEX IF NOT EXISTS ix_ai_generation_artifact_content_feature
    ON ai_generation_artifact (content_hash, feature);

CREATE INDEX IF NOT EXISTS ix_ai_generation_artifact_scope_owner
    ON ai_generation_artifact (scope, owner_user_id);

-- Idempotent migration safety: the table and indexes above can be applied
-- repeatedly while deploying the generation-path integration.
