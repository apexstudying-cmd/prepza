-- Student subscription lifecycle, entitlement usage, and refund ledger.
-- Additive/idempotent. Standard refund policy is configurable in SystemSetting.
-- IMPORTANT: this does not override statutory consumer rights; legal exceptions
-- must remain available even when the standard 24-hour policy has expired.

CREATE TABLE IF NOT EXISTS student_subscription (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES "user"(id),
    plan VARCHAR(20) NOT NULL CHECK (plan IN ('plus','pro')),
    paystack_plan_code VARCHAR(80) NOT NULL,
    paystack_subscription_code VARCHAR(100) UNIQUE,
    paystack_email_token VARCHAR(200),
    paystack_customer_code VARCHAR(100),
    status VARCHAR(30) NOT NULL DEFAULT 'active',
    cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE,
    next_payment_at TIMESTAMP NULL,
    current_period_start TIMESTAMP NULL,
    current_period_end TIMESTAMP NULL,
    initial_payment_id INTEGER NULL REFERENCES payment(id),
    latest_payment_id INTEGER NULL REFERENCES payment(id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, paystack_plan_code)
);

CREATE INDEX IF NOT EXISTS ix_student_subscription_user_status
ON student_subscription (user_id, status);

CREATE TABLE IF NOT EXISTS student_entitlement_usage (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES "user"(id),
    payment_id INTEGER NULL REFERENCES payment(id),
    feature VARCHAR(40) NOT NULL,
    units BIGINT NOT NULL CHECK (units > 0),
    request_count INTEGER NOT NULL DEFAULT 1 CHECK (request_count > 0),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_student_entitlement_usage_payment
ON student_entitlement_usage (payment_id, created_at);
CREATE INDEX IF NOT EXISTS ix_student_entitlement_usage_user_created
ON student_entitlement_usage (user_id, created_at);

CREATE TABLE IF NOT EXISTS student_refund_request (
    id BIGSERIAL PRIMARY KEY,
    payment_id INTEGER NOT NULL UNIQUE REFERENCES payment(id),
    user_id INTEGER NOT NULL REFERENCES "user"(id),
    requested_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(30) NOT NULL DEFAULT 'requested',
    requested_amount INTEGER NULL,
    approved_amount INTEGER NULL,
    consumed_value_kes INTEGER NOT NULL DEFAULT 0,
    retention_amount_kes INTEGER NOT NULL DEFAULT 0,
    reason VARCHAR(500),
    admin_user_id INTEGER NULL REFERENCES "user"(id),
    admin_reason VARCHAR(500),
    paystack_refund_id VARCHAR(100),
    paystack_status VARCHAR(30),
    processed_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_student_refund_request_user
ON student_refund_request (user_id, requested_at);

INSERT INTO system_setting (key, value)
VALUES
    ('student_refund_window_hours', '24'),
    ('student_refund_retention_percent', '20'),
    ('student_refund_full_zero_usage', 'true')
ON CONFLICT (key) DO NOTHING;
