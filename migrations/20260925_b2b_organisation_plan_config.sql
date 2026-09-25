-- Canonical B2B organisation subscription plan catalog.
-- Additive/idempotent. Values are launch defaults; admin changes are persisted
-- in this table and are versioned by the application.
CREATE TABLE IF NOT EXISTS organisation_plan_config (
    plan_code VARCHAR(20) PRIMARY KEY,
    monthly_fee_kes INTEGER NOT NULL,
    active_user_cap INTEGER NOT NULL,
    active_opportunities INTEGER NOT NULL DEFAULT 0,
    sponsored_campaigns INTEGER NOT NULL DEFAULT 0,
    candidate_search_window_days INTEGER NOT NULL DEFAULT 7,
    analytics_retention_days INTEGER NOT NULL DEFAULT 30,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    version INTEGER NOT NULL DEFAULT 1,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO organisation_plan_config
    (plan_code, monthly_fee_kes, active_user_cap, active_opportunities,
     sponsored_campaigns, candidate_search_window_days, analytics_retention_days)
VALUES
    ('launch', 2500, 250, 2, 1, 7, 30),
    ('growth', 7500, 1000, 10, 3, 30, 90),
    ('scale', 15000, 3000, 50, 10, 30, 365)
ON CONFLICT (plan_code) DO NOTHING;
