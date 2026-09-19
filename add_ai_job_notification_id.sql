-- Adds a durable link from a background AI/audio job to the
-- notification row that should be finalized when the job completes.
ALTER TABLE ai_job
ADD COLUMN IF NOT EXISTS notification_id INTEGER REFERENCES notification(id);
