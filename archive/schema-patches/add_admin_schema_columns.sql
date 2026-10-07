-- Prepza: Admin dashboard schema migration
-- Run this directly in the Supabase SQL editor (same pattern as
-- create_view_progress_table.sql). Safe to re-run: every statement
-- uses IF NOT EXISTS / ON CONFLICT so re-running won't error or
-- duplicate anything.
--
-- NOTE: "user" is a quoted reserved word in Postgres - keep the
-- double quotes exactly as below.

-- 1. created_at on user
-- Existing rows get NULL (unknown signup date) rather than a fake
-- backfilled timestamp - so the admin UI can distinguish "we don't
-- know when this user signed up" from a real date. New rows get the
-- current time automatically via the column default.
ALTER TABLE "user"
  ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW();

-- Only NEW rows get the DEFAULT NOW() applied automatically going
-- forward. Existing rows keep created_at = NULL until backfilled
-- (intentionally not backfilled here - see note above).

-- 2. signup_source on user
-- Nullable, no default. Populated from ?src= query param at signup.
-- NULL = organic / unknown source (e.g. everyone who signed up before
-- this column existed, or direct visits with no src param).
ALTER TABLE "user"
  ADD COLUMN IF NOT EXISTS signup_source VARCHAR(100);

-- 3. is_suspended on user
-- Defaults to false for all existing AND new rows - nobody gets
-- suspended by this migration itself.
ALTER TABLE "user"
  ADD COLUMN IF NOT EXISTS is_suspended BOOLEAN NOT NULL DEFAULT FALSE;

-- 4. system_setting table (key/value store for admin-configurable
-- site-wide settings: maintenance mode, announcement banner)
CREATE TABLE IF NOT EXISTS system_setting (
  id SERIAL PRIMARY KEY,
  key VARCHAR(50) UNIQUE NOT NULL,
  value TEXT NOT NULL DEFAULT ''
);

-- Seed the two settings rows if they don't already exist.
INSERT INTO system_setting (key, value)
VALUES ('maintenance_mode', 'false')
ON CONFLICT (key) DO NOTHING;

INSERT INTO system_setting (key, value)
VALUES ('announcement', '')
ON CONFLICT (key) DO NOTHING;

-- Verify (optional - run separately to confirm):
-- SELECT column_name, data_type, is_nullable, column_default
--   FROM information_schema.columns
--   WHERE table_name = 'user'
--   ORDER BY ordinal_position;
-- SELECT * FROM system_setting;
