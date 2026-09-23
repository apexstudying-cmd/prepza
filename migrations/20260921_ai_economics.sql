-- Prepza AI economics / Ada metering
-- Safe, additive Supabase/PostgreSQL migration.
-- Existing usage/payment data is not altered or deleted.

CREATE TABLE IF NOT EXISTS student_plan_config (
    plan_code VARCHAR(20) PRIMARY KEY,
    display_name VARCHAR(40) NOT NULL,
    price_kes INTEGER NOT NULL DEFAULT 0,
    billing_period VARCHAR(20) NOT NULL DEFAULT 'month',
    quota_period VARCHAR(20) NOT NULL DEFAULT 'month',
    ada_monthly_units BIGINT NOT NULL DEFAULT 0,
    ada_daily_units BIGINT NOT NULL DEFAULT 0,
    ada_max_output_tokens INTEGER NOT NULL DEFAULT 800,
    podcast_minutes INTEGER NOT NULL DEFAULT 0,
    summary_pages INTEGER NOT NULL DEFAULT 0,
    questions INTEGER NOT NULL DEFAULT 0,
    mind_map_nodes INTEGER NOT NULL DEFAULT 0,
    flashcards INTEGER NOT NULL DEFAULT 0,
    offline_study BOOLEAN NOT NULL DEFAULT FALSE,
    premium_library BOOLEAN NOT NULL DEFAULT FALSE,
    study_hub_uploads BOOLEAN NOT NULL DEFAULT TRUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by INTEGER
);

CREATE TABLE IF NOT EXISTS ada_usage_day (
    user_id INTEGER NOT NULL,
    usage_date DATE NOT NULL,
    ada_units BIGINT NOT NULL DEFAULT 0,
    requests INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, usage_date)
);

CREATE TABLE IF NOT EXISTS ada_usage_month (
    user_id INTEGER NOT NULL,
    period_start DATE NOT NULL,
    ada_units BIGINT NOT NULL DEFAULT 0,
    requests INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, period_start)
);

CREATE TABLE IF NOT EXISTS ada_request_usage (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    plan_code VARCHAR(20) NOT NULL,
    model VARCHAR(100) NOT NULL,
    provider VARCHAR(40),
    input_tokens INTEGER NOT NULL DEFAULT 0,
    cached_tokens INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    ada_units BIGINT NOT NULL DEFAULT 0,
    cost_usd NUMERIC(14,8) NOT NULL DEFAULT 0,
    request_key VARCHAR(120),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_ada_request_usage_user_created
    ON ada_request_usage (user_id, created_at);

CREATE TABLE IF NOT EXISTS ai_economics_change_log (
    id BIGSERIAL PRIMARY KEY,
    admin_user_id INTEGER NOT NULL,
    plan_code VARCHAR(20) NOT NULL,
    changes JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO student_plan_config (
    plan_code, display_name, price_kes, billing_period, quota_period,
    ada_monthly_units, ada_daily_units, ada_max_output_tokens,
    podcast_minutes, summary_pages, questions, mind_map_nodes,
    flashcards, offline_study, premium_library, study_hub_uploads
) VALUES
('free','Free',0,'month','month',500000,20000,800,10,10,20,30,100,FALSE,FALSE,TRUE),
('plus','Plus',499,'month','month',2500000,100000,1200,120,40,100,150,300,TRUE,TRUE,TRUE),
('pro','Pro',999,'month','month',6000000,250000,1600,350,100,210,350,600,TRUE,TRUE,TRUE)
ON CONFLICT (plan_code) DO NOTHING;
