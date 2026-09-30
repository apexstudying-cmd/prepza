-- Reconcile AI generation in-flight family tables used by ai_generation_store.py.
-- These are also created lazily by the runtime; keeping them here makes the
-- production schema explicit and avoids first-request DDL.
CREATE TABLE IF NOT EXISTS ai_generation_inflight (
  base_fingerprint VARCHAR(128) PRIMARY KEY,
  artifact_id BIGINT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'generating',
  lease_token VARCHAR(128) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_ai_generation_inflight_artifact
  ON ai_generation_inflight (artifact_id);

CREATE TABLE IF NOT EXISTS ai_generation_subscriber (
  id BIGSERIAL PRIMARY KEY,
  base_fingerprint VARCHAR(128) NOT NULL,
  user_id INTEGER NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'waiting',
  artifact_id BIGINT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at TIMESTAMP NULL
);
CREATE INDEX IF NOT EXISTS ix_ai_generation_subscriber_family
  ON ai_generation_subscriber (base_fingerprint, status, created_at);
