-- Add a non-secret worker identity so heartbeat/recovery telemetry can map to one GPU safely.
BEGIN;
ALTER TABLE kokoro_gpu_workers ADD COLUMN IF NOT EXISTS worker_id VARCHAR(64);
CREATE UNIQUE INDEX IF NOT EXISTS uq_kokoro_gpu_workers_worker_id
  ON kokoro_gpu_workers(worker_id)
  WHERE worker_id IS NOT NULL;
COMMIT;
