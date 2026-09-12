-- Fenced leases prevent a stale worker from publishing after another worker
-- has reclaimed the same generation artifact.
ALTER TABLE ai_generation_artifact
    ADD COLUMN IF NOT EXISTS lease_token VARCHAR(64);

CREATE INDEX IF NOT EXISTS ix_ai_generation_artifact_generating_lease
    ON ai_generation_artifact (id, lease_token)
    WHERE status = 'generating';
