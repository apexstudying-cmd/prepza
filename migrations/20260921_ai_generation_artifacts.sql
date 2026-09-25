-- Canonical, fingerprinted AI generation artifacts and reusable variant families.
-- Additive/idempotent PostgreSQL migration.
-- GeneratedMaterial remains the application-facing projection.

CREATE TABLE IF NOT EXISTS ai_generation_artifact (
    id BIGSERIAL PRIMARY KEY,
    fingerprint VARCHAR(128) NOT NULL UNIQUE,
    content_hash VARCHAR(128) NOT NULL,
    feature VARCHAR(40) NOT NULL,
    parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
    prompt_version VARCHAR(80) NOT NULL,
    schema_version VARCHAR(80) NOT NULL,
    scope VARCHAR(20) NOT NULL DEFAULT 'shared',
    owner_user_id INTEGER NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'generating',
    payload JSONB NULL,
    error_message VARCHAR(4000) NULL,
    lease_token VARCHAR(128) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP NULL,
    CONSTRAINT ck_ai_generation_artifact_scope
        CHECK (scope IN ('shared', 'private')),
    CONSTRAINT ck_ai_generation_artifact_scope_owner
        CHECK (
            (scope = 'shared' AND owner_user_id IS NULL)
            OR
            (scope = 'private' AND owner_user_id IS NOT NULL)
        )
);

CREATE INDEX IF NOT EXISTS ix_ai_generation_artifact_content_feature
    ON ai_generation_artifact (content_hash, feature);

CREATE INDEX IF NOT EXISTS ix_ai_generation_artifact_status_updated
    ON ai_generation_artifact (status, updated_at);

CREATE INDEX IF NOT EXISTS ix_ai_generation_artifact_owner
    ON ai_generation_artifact (owner_user_id);

CREATE TABLE IF NOT EXISTS ai_generation_variant_family (
    base_fingerprint VARCHAR(64) PRIMARY KEY,
    feature VARCHAR(40) NOT NULL,
    base_parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
    next_variant SMALLINT NOT NULL DEFAULT 1,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ai_generation_variant_access (
    user_id INTEGER NOT NULL,
    base_fingerprint VARCHAR(64) NOT NULL,
    variant SMALLINT NOT NULL,
    artifact_id BIGINT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'reserved',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, base_fingerprint, variant),
    CONSTRAINT ck_ai_generation_variant_status
        CHECK (status IN ('reserved', 'ready'))
);

CREATE INDEX IF NOT EXISTS ix_ai_generation_variant_access_family
    ON ai_generation_variant_access (base_fingerprint, variant, status);

CREATE INDEX IF NOT EXISTS ix_ai_generation_variant_access_artifact
    ON ai_generation_variant_access (artifact_id);
