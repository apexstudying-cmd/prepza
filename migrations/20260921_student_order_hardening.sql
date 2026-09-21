-- Student-order hardening and legacy backfill.
-- The order ledger is the fulfillment authority for all content/subscription
-- payments. Existing payment rows are copied once so the new entitlement
-- gate does not break legitimate historical purchases.
--
-- Safe to run after add_student_orders.sql: all DDL is idempotent and
-- payment_id is UNIQUE, so rerunning the backfill does not duplicate orders.

CREATE TABLE IF NOT EXISTS student_order (
    id BIGSERIAL PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    user_id INTEGER NOT NULL REFERENCES "user"(id),
    payment_id INTEGER NOT NULL UNIQUE REFERENCES payment(id),
    order_type VARCHAR(30) NOT NULL,
    item_id INTEGER NULL REFERENCES content_item(id),
    item_title_snapshot VARCHAR(200) NOT NULL,
    item_file_url_snapshot VARCHAR(500) NULL,
    plan VARCHAR(20) NULL,
    quantity INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
    unit_amount INTEGER NOT NULL CHECK (unit_amount >= 0),
    total_amount INTEGER NOT NULL CHECK (total_amount >= 0),
    currency VARCHAR(3) NOT NULL DEFAULT 'KES',
    requested_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    fulfillment_payload JSONB NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    paid_at TIMESTAMP NULL,
    fulfilled_at TIMESTAMP NULL,
    refunded_at TIMESTAMP NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    checkout_url TEXT
);

ALTER TABLE student_order
    ADD COLUMN IF NOT EXISTS item_file_url_snapshot VARCHAR(500) NULL;

CREATE INDEX IF NOT EXISTS ix_student_order_user_created
    ON student_order (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_student_order_status
    ON student_order (status);
CREATE INDEX IF NOT EXISTS ix_student_order_item
    ON student_order (item_id);

INSERT INTO student_order (
    order_number,
    user_id,
    payment_id,
    order_type,
    item_id,
    item_title_snapshot,
    item_file_url_snapshot,
    plan,
    quantity,
    unit_amount,
    total_amount,
    currency,
    requested_payload,
    fulfillment_payload,
    status,
    created_at,
    paid_at,
    fulfilled_at,
    refunded_at,
    updated_at
)
SELECT
    'PZA-LEGACY-' || p.id::text,
    p.user_id,
    p.id,
    p.payment_type,
    p.content_item_id,
    CASE
        WHEN p.payment_type = 'content' THEN COALESCE(ci.title, 'Purchased content')
        WHEN p.plan = 'semester' THEN 'Plus Plan'
        WHEN p.plan = 'annual' THEN 'Pro Plan'
        ELSE 'Subscription'
    END,
    CASE WHEN p.payment_type = 'content' THEN ci.file_url ELSE NULL END,
    p.plan,
    1,
    p.amount,
    p.amount,
    'KES',
    jsonb_build_object(
        'payment_type', p.payment_type,
        'content_item_id', p.content_item_id,
        'content_title', CASE WHEN p.payment_type = 'content' THEN ci.title ELSE NULL END,
        'plan', p.plan,
        'quantity', 1,
        'legacy_backfill', true
    ),
    CASE WHEN p.status = 'success' THEN jsonb_build_object(
        'payment_id', p.id,
        'content_item_id', p.content_item_id,
        'plan', p.plan,
        'user_id', p.user_id,
        'quantity', 1,
        'fulfilled_exactly_as_requested', true,
        'legacy_backfill', true
    ) ELSE NULL END,
    CASE
        WHEN p.status = 'success' THEN 'fulfilled'
        WHEN p.status = 'refunded' THEN 'refunded'
        WHEN p.status = 'pending' THEN 'pending'
        ELSE 'failed'
    END,
    COALESCE(p.created_at, CURRENT_TIMESTAMP),
    CASE WHEN p.status IN ('success', 'refunded') THEN COALESCE(p.created_at, CURRENT_TIMESTAMP) ELSE NULL END,
    CASE WHEN p.status = 'success' THEN COALESCE(p.created_at, CURRENT_TIMESTAMP) ELSE NULL END,
    CASE WHEN p.status = 'refunded' THEN COALESCE(p.created_at, CURRENT_TIMESTAMP) ELSE NULL END,
    CURRENT_TIMESTAMP
FROM payment p
LEFT JOIN content_item ci ON ci.id = p.content_item_id
WHERE p.user_id IS NOT NULL
  AND p.payment_type IN ('content', 'subscription')
  AND NOT EXISTS (
      SELECT 1 FROM student_order existing WHERE existing.payment_id = p.id
  );

-- After the backfill, a new paid content payment without an order is an
-- invariant violation and must not be allowed to unlock content.


-- Database-level invariants: even if application code is bypassed or
-- regresses later, an order cannot represent an impossible fulfillment.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_student_order_quantity_positive'
    ) THEN
        ALTER TABLE student_order
        ADD CONSTRAINT ck_student_order_quantity_positive
        CHECK (quantity = 1);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_student_order_total_matches_unit'
    ) THEN
        ALTER TABLE student_order
        ADD CONSTRAINT ck_student_order_total_matches_unit
        CHECK (total_amount = unit_amount * quantity);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_student_order_currency_kes'
    ) THEN
        ALTER TABLE student_order
        ADD CONSTRAINT ck_student_order_currency_kes
        CHECK (currency = 'KES');
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_student_order_type_snapshot'
    ) THEN
        ALTER TABLE student_order
        ADD CONSTRAINT ck_student_order_type_snapshot
        CHECK (
            (order_type = 'subscription' AND item_id IS NULL AND plan IN ('semester', 'annual'))
            OR
            (order_type = 'content' AND item_id IS NOT NULL AND plan IS NULL)
        );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_student_order_plan_allowed'
    ) THEN
        ALTER TABLE student_order
        ADD CONSTRAINT ck_student_order_plan_allowed
        CHECK (
            (order_type = 'subscription' AND plan IN ('semester', 'annual'))
            OR
            (order_type = 'content' AND plan IS NULL)
        );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_student_order_type_allowed'
    ) THEN
        ALTER TABLE student_order
        ADD CONSTRAINT ck_student_order_type_allowed
        CHECK (order_type IN ('subscription', 'content'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_student_order_status_allowed'
    ) THEN
        ALTER TABLE student_order
        ADD CONSTRAINT ck_student_order_status_allowed
        CHECK (status IN ('pending', 'paid', 'fulfilled', 'failed', 'refunded', 'cancelled'));
    END IF;
    END IF;
END $$;
