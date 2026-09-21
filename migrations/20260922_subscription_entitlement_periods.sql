-- Exact paid subscription entitlement periods.
-- A successful payment can be created before its entitlement period begins
-- when periods are intentionally stacked. The starts_at boundary prevents a
-- future paid period from granting its plan early.
ALTER TABLE payment
  ADD COLUMN IF NOT EXISTS subscription_starts_at TIMESTAMP NULL;

WITH ordered AS (
  SELECT
    id,
    user_id,
    created_at,
    LAG(subscription_expires_at) OVER (
      PARTITION BY user_id
      ORDER BY created_at ASC, id ASC
    ) AS previous_expiry
  FROM payment
  WHERE payment_type = 'subscription'
    AND status = 'success'
    AND subscription_expires_at IS NOT NULL
)
UPDATE payment AS p
SET subscription_starts_at = CASE
  WHEN o.previous_expiry IS NOT NULL
       AND o.previous_expiry > COALESCE(o.created_at, CURRENT_TIMESTAMP)
    THEN o.previous_expiry
  ELSE COALESCE(o.created_at, CURRENT_TIMESTAMP)
END
FROM ordered AS o
WHERE p.id = o.id
  AND p.subscription_starts_at IS NULL;

CREATE INDEX IF NOT EXISTS ix_payment_subscription_entitlement_period
  ON payment (user_id, payment_type, status, subscription_starts_at, subscription_expires_at);
