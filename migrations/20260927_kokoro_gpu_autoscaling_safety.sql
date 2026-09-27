-- Kokoro GPU autoscaling safety state and decision audit.
-- Apply after the application code is deployed; the application defaults to dry-run.
BEGIN;

CREATE TABLE IF NOT EXISTS kokoro_gpu_workers (
    id BIGSERIAL PRIMARY KEY,
    provider VARCHAR(32) NOT NULL DEFAULT 'vast',
    instance_id BIGINT NOT NULL UNIQUE,
    offer_id BIGINT,
    gpu_name VARCHAR(120) NOT NULL,
    gpu_vram_gb NUMERIC(8,2),
    status VARCHAR(32) NOT NULL DEFAULT 'starting',
    worker_index INTEGER NOT NULL DEFAULT 1,
    worker_capacity INTEGER NOT NULL DEFAULT 1,
    price_usd_per_hour NUMERIC(12,6),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_job_at TIMESTAMP,
    last_idle_at TIMESTAMP,
    last_heartbeat_at TIMESTAMP,
    vram_used_gb NUMERIC(8,2),
    vram_total_gb NUMERIC(8,2),
    last_error VARCHAR(1000),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ix_kokoro_gpu_workers_status
    ON kokoro_gpu_workers(status);
CREATE INDEX IF NOT EXISTS ix_kokoro_gpu_workers_heartbeat
    ON kokoro_gpu_workers(last_heartbeat_at);

CREATE TABLE IF NOT EXISTS kokoro_gpu_scaling_decisions (
    id BIGSERIAL PRIMARY KEY,
    action VARCHAR(32) NOT NULL,
    reason_code VARCHAR(80) NOT NULL,
    reason_text VARCHAR(1000) NOT NULL,
    dry_run BOOLEAN NOT NULL DEFAULT TRUE,
    pending_jobs INTEGER NOT NULL DEFAULT 0,
    processing_jobs INTEGER NOT NULL DEFAULT 0,
    queue_depth INTEGER NOT NULL DEFAULT 0,
    oldest_pending_age_seconds INTEGER,
    queued_audio_seconds NUMERIC(14,2) NOT NULL DEFAULT 0,
    current_workers INTEGER NOT NULL DEFAULT 0,
    desired_workers INTEGER NOT NULL DEFAULT 0,
    target_workers INTEGER NOT NULL DEFAULT 0,
    max_workers INTEGER NOT NULL DEFAULT 1,
    max_pending_jobs_per_worker INTEGER NOT NULL DEFAULT 3,
    max_pending_age_seconds INTEGER NOT NULL DEFAULT 120,
    max_gpu_price_usd_per_hour NUMERIC(12,6),
    max_gpu_hourly_spend_usd NUMERIC(12,6),
    estimated_incremental_hourly_usd NUMERIC(12,6),
    gpu_name VARCHAR(120),
    gpu_vram_gb NUMERIC(8,2),
    vram_used_gb NUMERIC(8,2),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ix_kokoro_gpu_scaling_decisions_created
    ON kokoro_gpu_scaling_decisions(created_at DESC);
CREATE INDEX IF NOT EXISTS ix_kokoro_gpu_scaling_decisions_action
    ON kokoro_gpu_scaling_decisions(action, created_at DESC);

COMMIT;
