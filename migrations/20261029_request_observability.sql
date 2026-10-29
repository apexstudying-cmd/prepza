-- Low-volume metadata only: capture server errors and slow HTTP requests.
-- Request bodies, query strings, cookies, IP addresses, and user IDs are never stored.
CREATE TABLE IF NOT EXISTS request_observability_event (
    id BIGSERIAL PRIMARY KEY,
    request_id VARCHAR(64) NOT NULL,
    method VARCHAR(12) NOT NULL,
    route VARCHAR(160) NOT NULL,
    status_code INTEGER NOT NULL CHECK (status_code BETWEEN 100 AND 599),
    duration_ms DOUBLE PRECISION NULL,
    occurred_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_request_observability_event_request_id
    ON request_observability_event (request_id);
CREATE INDEX IF NOT EXISTS ix_request_observability_event_time
    ON request_observability_event (occurred_at DESC);
CREATE INDEX IF NOT EXISTS ix_request_observability_status_time
    ON request_observability_event (status_code, occurred_at DESC);

-- Retain only a bounded operational window. Cleanup is run opportunistically
-- when an event is recorded, not on every healthy request.
