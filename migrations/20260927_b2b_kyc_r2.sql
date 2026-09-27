ALTER TABLE organisation_kyc_document
  ADD COLUMN IF NOT EXISTS size_bytes BIGINT,
  ADD COLUMN IF NOT EXISTS sha256 VARCHAR(64),
  ADD COLUMN IF NOT EXISTS mime_type VARCHAR(120),
  ADD COLUMN IF NOT EXISTS storage_provider VARCHAR(20) NOT NULL DEFAULT 'supabase';

CREATE INDEX IF NOT EXISTS ix_org_kyc_org_status
  ON organisation_kyc_document(organisation_id,status,created_at DESC);
