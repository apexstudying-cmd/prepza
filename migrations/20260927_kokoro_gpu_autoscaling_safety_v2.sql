-- Final Kokoro autoscaler safety state: worker ownership, recovery fencing,
-- host RAM/VRAM requirements, and provider-credit affordability telemetry.
BEGIN;

ALTER TABLE kokoro_gpu_workers
  ADD COLUMN IF NOT EXISTS host_ram_gb NUMERIC(8,2),
  ADD COLUMN IF NOT EXISTS required_vram_gb NUMERIC(8,2),
  ADD COLUMN IF NOT EXISTS required_host_ram_gb NUMERIC(8,2);

ALTER TABLE kokoro_gpu_scaling_decisions
  ADD COLUMN IF NOT EXISTS provider_credit_usd NUMERIC(12,6),
  ADD COLUMN IF NOT EXISTS provider_credit_reserve_usd NUMERIC(12,6),
  ADD COLUMN IF NOT EXISTS host_ram_gb NUMERIC(8,2),
  ADD COLUMN IF NOT EXISTS required_vram_gb NUMERIC(8,2),
  ADD COLUMN IF NOT EXISTS required_host_ram_gb NUMERIC(8,2),
  ADD COLUMN IF NOT EXISTS projected_hourly_spend_usd NUMERIC(12,6),
  ADD COLUMN IF NOT EXISTS decision_context JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE ai_job
  ADD COLUMN IF NOT EXISTS claimed_worker_id VARCHAR(64);

CREATE INDEX IF NOT EXISTS ix_ai_job_claimed_worker_id
  ON ai_job(claimed_worker_id)
  WHERE claimed_worker_id IS NOT NULL;

COMMIT;
