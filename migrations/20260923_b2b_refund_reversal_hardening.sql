-- B2B refund/reversal lifecycle hardening.
-- Refund state is provider-driven; campaign value is reversed only after
-- Paystack confirms refund.processed. Refund initiation freezes delivery.
ALTER TABLE b2b_payment
    ADD COLUMN IF NOT EXISTS refund_status VARCHAR(30),
    ADD COLUMN IF NOT EXISTS refunded_amount_minor BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS refund_reference VARCHAR(120),
    ADD COLUMN IF NOT EXISTS refund_requested_at TIMESTAMP,
    ADD COLUMN IF NOT EXISTS refund_processed_at TIMESTAMP;

CREATE INDEX IF NOT EXISTS ix_b2b_payment_refund_reference
    ON b2b_payment (refund_reference);

CREATE INDEX IF NOT EXISTS ix_b2b_payment_refund_status
    ON b2b_payment (refund_status);

ALTER TABLE discovery_campaign
    ADD COLUMN IF NOT EXISTS refund_previous_status VARCHAR(30);

