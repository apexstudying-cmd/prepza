-- Prepza email OTP authentication
CREATE TABLE IF NOT EXISTS auth_otp (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    purpose VARCHAR(30) NOT NULL,
    target VARCHAR(320) NOT NULL,
    code_hash VARCHAR(64) NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    request_ip VARCHAR(64),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    consumed_at TIMESTAMP NULL
);
CREATE INDEX IF NOT EXISTS ix_auth_otp_user_purpose_created
    ON auth_otp(user_id, purpose, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_auth_otp_target_created
    ON auth_otp(target, purpose, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_auth_otp_ip_created
    ON auth_otp(request_ip, purpose, created_at DESC);

INSERT INTO system_setting(key, value) VALUES
('otp_enabled','true'),
('otp_length','6'),
('otp_expiry_minutes','10'),
('otp_max_attempts','5'),
('otp_resend_cooldown_seconds','60'),
('otp_max_sends_per_target_hour','5'),
('otp_max_sends_per_ip_hour','20')
ON CONFLICT (key) DO NOTHING;
