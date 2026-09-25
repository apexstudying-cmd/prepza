-- Add an immutable allowance snapshot to each subscription payment.
-- New purchases/renewals populate it from student_plan_config at fulfillment time.
-- Existing rows intentionally remain NULL because their historical admin
-- configuration cannot be reconstructed safely from the payment row alone.
ALTER TABLE payment
  ADD COLUMN IF NOT EXISTS subscription_allowance_snapshot JSONB;

COMMENT ON COLUMN payment.subscription_allowance_snapshot IS
  'Immutable student-plan allowance snapshot captured when this subscription payment is fulfilled; used for refund accounting.';
