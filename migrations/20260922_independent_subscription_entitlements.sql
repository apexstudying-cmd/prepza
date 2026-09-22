-- Prepza subscription entitlement policy:
-- Every successful subscription payment owns its own independent period.
-- Overlapping purchases are allowed:
--   Plus Sep 10 -> Oct 10
--   Pro  Sep 20 -> Oct 20
-- The latest active plan controls the displayed tier, while active
-- entitlements may coexist for quota/feature accounting.
--
-- IMPORTANT: This is an entitlement migration, not a Paystack billing change.
-- Paystack's recurring billing schedule remains provider-controlled.

ALTER TABLE payment
    ADD COLUMN IF NOT EXISTS subscription_starts_at TIMESTAMP NULL;

UPDATE payment
SET subscription_starts_at = COALESCE(created_at, CURRENT_TIMESTAMP)
WHERE payment_type = 'subscription'
  AND status = 'success'
  AND subscription_expires_at IS NOT NULL
  AND subscription_starts_at IS NULL;

-- Existing successful rows may have been written by the temporary
-- stacked-period implementation. Rebuild their own period boundaries from
-- their original payment timestamp so one refund cannot rewrite another
-- payment's entitlement.
UPDATE payment
SET subscription_starts_at = COALESCE(created_at, subscription_starts_at),
    subscription_expires_at = COALESCE(created_at, CURRENT_TIMESTAMP) + INTERVAL '1 month'
WHERE payment_type = 'subscription'
  AND status = 'success'
  AND created_at IS NOT NULL
  AND subscription_expires_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_payment_subscription_entitlement_period
    ON payment (user_id, payment_type, status, subscription_starts_at, subscription_expires_at);
