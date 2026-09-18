-- Organisation promotion billing
-- One-time Paystack payments. Existing student/content/subscription payments remain unchanged.
ALTER TABLE payment ADD COLUMN IF NOT EXISTS organisation_id INTEGER REFERENCES organisation(id);
ALTER TABLE payment ADD COLUMN IF NOT EXISTS opportunity_promotion_id INTEGER REFERENCES opportunity_promotion(id);
CREATE INDEX IF NOT EXISTS ix_payment_organisation_id ON payment (organisation_id);
CREATE INDEX IF NOT EXISTS ix_payment_opportunity_promotion_id ON payment (opportunity_promotion_id);
