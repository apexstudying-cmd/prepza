-- Consolidate historical StudyTimeLog feature rows into the single
-- Study Hub learning-time row per user and Nairobi calendar day.
--
-- The previous implementation stored independent feature rows. The new
-- contract treats feature/document as context and Study Hub as the single
-- authoritative learning total. Preserve the historical total, capped at
-- the existing daily anti-gaming ceiling, before replacing the old rows.

CREATE TEMP TABLE study_time_log_migration AS
SELECT
    user_id,
    activity_date,
    LEAST(SUM(study_time_seconds), 43200)::integer AS study_time_seconds
FROM study_time_log
GROUP BY user_id, activity_date;

DELETE FROM study_time_log;

INSERT INTO study_time_log (
    user_id,
    activity_date,
    feature,
    study_time_seconds,
    last_heartbeat_at
)
SELECT
    user_id,
    activity_date,
    'study_hub',
    study_time_seconds,
    NULL
FROM study_time_log_migration;

DROP TABLE study_time_log_migration;
