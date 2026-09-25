-- B2B premium organisation portal
ALTER TABLE opportunity
  ADD COLUMN IF NOT EXISTS organic_free_impression_cap INTEGER NOT NULL DEFAULT 5000,
  ADD COLUMN IF NOT EXISTS organic_free_cap_reached_at TIMESTAMP;

CREATE TABLE IF NOT EXISTS opportunity_view_event (
  id BIGSERIAL PRIMARY KEY,
  opportunity_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  source VARCHAR(20) NOT NULL DEFAULT 'organic',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_opp_view_event_opp_created ON opportunity_view_event(opportunity_id,created_at);
CREATE INDEX IF NOT EXISTS ix_opp_view_event_user_opp ON opportunity_view_event(user_id,opportunity_id,created_at);

CREATE TABLE IF NOT EXISTS organisation_kyc_document (
  id BIGSERIAL PRIMARY KEY,
  organisation_id INTEGER NOT NULL,
  document_type VARCHAR(60) NOT NULL,
  file_name VARCHAR(255),
  storage_path TEXT,
  status VARCHAR(30) NOT NULL DEFAULT 'pending',
  admin_notes TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  reviewed_at TIMESTAMP,
  reviewed_by INTEGER
);

CREATE TABLE IF NOT EXISTS b2b_invoice (
  id BIGSERIAL PRIMARY KEY,
  organisation_id INTEGER NOT NULL,
  campaign_id BIGINT,
  invoice_number VARCHAR(80) NOT NULL UNIQUE,
  currency VARCHAR(3) NOT NULL DEFAULT 'KES',
  subtotal_minor BIGINT NOT NULL,
  processing_fee_minor BIGINT NOT NULL DEFAULT 0,
  total_minor BIGINT NOT NULL,
  status VARCHAR(30) NOT NULL DEFAULT 'pro_forma',
  payment_method VARCHAR(30) NOT NULL DEFAULT 'bank_transfer',
  due_at TIMESTAMP,
  paid_at TIMESTAMP,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_b2b_invoice_org_created ON b2b_invoice(organisation_id,created_at DESC);


ALTER TABLE b2b_invoice ADD COLUMN IF NOT EXISTS etims_status VARCHAR(30) NOT NULL DEFAULT 'not_issued';
ALTER TABLE b2b_invoice ADD COLUMN IF NOT EXISTS etims_invoice_number VARCHAR(120);
ALTER TABLE b2b_invoice ADD COLUMN IF NOT EXISTS etims_control_code VARCHAR(120);
ALTER TABLE b2b_invoice ADD COLUMN IF NOT EXISTS etims_issued_at TIMESTAMP;


-- Sponsored delivery analytics can be below KES 1 per event (for example,
-- KES 350 CPM = KES 0.35 per impression). Keep accounting in minor units in
-- the B2B ledger and retain the event's human-readable amount at four decimals.
ALTER TABLE discovery_event
  ALTER COLUMN amount_kes TYPE NUMERIC(12,4)
  USING amount_kes::numeric;
