-- Prepza AI generation job request integrity
-- Stores the exact generation configuration requested by the student.
-- Run this once against the production Supabase/Postgres database before
-- deploying code that writes AiJob.generation_parameters.

ALTER TABLE ai_job
    ADD COLUMN IF NOT EXISTS generation_parameters JSONB NOT NULL DEFAULT '{}'::jsonb;

COMMENT ON COLUMN ai_job.generation_parameters IS
    'Immutable student-requested generation configuration used by the generation worker.';
