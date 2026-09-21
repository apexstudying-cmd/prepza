-- Durable student order ledger.
-- The order snapshots exactly what was requested at checkout. Payment remains
-- the authoritative money/provider record; this table is the fulfillment record.

CREATE TABLE IF NOT EXISTS student_order (
    id BIGSERIAL PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    user_id INTEGER NOT NULL REFERENCES "user"(id),
    payment_id INTEGER NOT NULL UNIQUE REFERENCES payment(id),
    order_type VARCHAR(30) NOT NULL,
    item_id INTEGER NULL REFERENCES content_item(id),
    item_title_snapshot VARCHAR(200) NOT NULL,
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
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_student_order_user_created
    ON student_order (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_student_order_status
    ON student_order (status);

CREATE INDEX IF NOT EXISTS ix_student_order_item
    ON student_order (item_id);
