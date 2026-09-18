-- Launch usage/billing schema for Prepza.
-- Additive and idempotent. The application also creates these tables on startup
-- for environments where explicit migration execution is not available.

CREATE TABLE IF NOT EXISTS student_ai_usage (
    user_id INTEGER NOT NULL,
    period_start DATE NOT NULL,
    feature VARCHAR(40) NOT NULL,
    units INTEGER NOT NULL DEFAULT 0,
    requests INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, period_start, feature)
);

CREATE TABLE IF NOT EXISTS product_activity_day (
    user_id INTEGER NOT NULL,
    activity_date DATE NOT NULL,
    sessions INTEGER NOT NULL DEFAULT 0,
    engaged_seconds INTEGER NOT NULL DEFAULT 0,
    core_actions INTEGER NOT NULL DEFAULT 0,
    last_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, activity_date)
);

CREATE INDEX IF NOT EXISTS ix_product_activity_day_date_user
    ON product_activity_day (activity_date, user_id);

CREATE TABLE IF NOT EXISTS organisation_billing (
    organisation_id INTEGER PRIMARY KEY,
    plan_code VARCHAR(30) NOT NULL DEFAULT 'launch',
    status VARCHAR(20) NOT NULL DEFAULT 'trial',
    monthly_fee_kes INTEGER,
    active_user_cap INTEGER,
    started_at TIMESTAMP,
    expires_at TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS organisation_campaign_meter (
    organisation_id INTEGER NOT NULL,
    period_start DATE NOT NULL,
    impressions INTEGER NOT NULL DEFAULT 0,
    clicks INTEGER NOT NULL DEFAULT 0,
    applications INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (organisation_id, period_start)
);
