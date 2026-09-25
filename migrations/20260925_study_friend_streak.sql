-- Shared 1:1 study streaks. Qualification remains application-level:
-- both participants must accumulate at least 10 minutes of StudyTimeLog
-- on the same Africa/Nairobi calendar day.
CREATE TABLE IF NOT EXISTS study_friend_streak (
    id BIGSERIAL PRIMARY KEY,
    user_a_id INTEGER NOT NULL,
    user_b_id INTEGER NOT NULL,
    invited_by INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    current_streak INTEGER NOT NULL DEFAULT 0,
    longest_streak INTEGER NOT NULL DEFAULT 0,
    last_shared_date DATE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_a_id, user_b_id)
);
CREATE TABLE IF NOT EXISTS study_friend_streak_activity (
    id VARCHAR(36) PRIMARY KEY,
    streak_id BIGINT NOT NULL,
    user_a_id INTEGER NOT NULL,
    user_b_id INTEGER NOT NULL,
    activity_date DATE NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(streak_id, activity_date)
);