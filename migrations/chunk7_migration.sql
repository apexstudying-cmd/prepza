-- ============================================================
-- Chunk 7: XP / Achievements / Streaks
-- Run in the Supabase SQL editor (or via your usual migration path).
-- Matches the SQLAlchemy models added to app.py - if you rename a
-- column there, update it here too.
-- ============================================================

-- One row per user: running streak counters.
CREATE TABLE IF NOT EXISTS study_streak (
    id                SERIAL PRIMARY KEY,
    user_id           INTEGER NOT NULL UNIQUE REFERENCES "user"(id),
    current_streak    INTEGER NOT NULL DEFAULT 0,
    longest_streak    INTEGER NOT NULL DEFAULT 0,
    last_study_date   DATE,
    updated_at        TIMESTAMP
);

-- One row per user per document per calendar day that had a
-- qualifying study action. Powers the streak calendar and caps
-- "document studied" XP to once per document per day.
CREATE TABLE IF NOT EXISTS study_activity_log (
    id                    SERIAL PRIMARY KEY,
    user_id               INTEGER NOT NULL REFERENCES "user"(id),
    document_content_id   INTEGER REFERENCES document_content(id),
    activity_date         DATE NOT NULL,
    created_at            TIMESTAMP,
    CONSTRAINT uq_study_activity_user_doc_date
        UNIQUE (user_id, document_content_id, activity_date)
);
CREATE INDEX IF NOT EXISTS ix_study_activity_log_user_date
    ON study_activity_log (user_id, activity_date);

-- One row per quiz completion (not deduplicated - every attempt counts).
CREATE TABLE IF NOT EXISTS quiz_attempt (
    id                      SERIAL PRIMARY KEY,
    user_id                 INTEGER NOT NULL REFERENCES "user"(id),
    generated_material_id   INTEGER NOT NULL REFERENCES generated_material(id),
    document_content_id     INTEGER NOT NULL REFERENCES document_content(id),
    score_percent           INTEGER,
    created_at              TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_quiz_attempt_user
    ON quiz_attempt (user_id);

-- One row per completed flashcard review session.
CREATE TABLE IF NOT EXISTS flashcard_session (
    id                      SERIAL PRIMARY KEY,
    user_id                 INTEGER NOT NULL REFERENCES "user"(id),
    generated_material_id   INTEGER NOT NULL REFERENCES generated_material(id),
    document_content_id     INTEGER NOT NULL REFERENCES document_content(id),
    cards_reviewed          INTEGER,
    created_at              TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_flashcard_session_user
    ON flashcard_session (user_id);

-- Unlocked achievements. The catalog itself lives in app.py
-- (ACHIEVEMENT_DEFINITIONS), not in a table - MVP tradeoff, same as
-- the fixed XP_* constants.
CREATE TABLE IF NOT EXISTS user_achievement (
    id                  SERIAL PRIMARY KEY,
    user_id             INTEGER NOT NULL REFERENCES "user"(id),
    achievement_code    VARCHAR(40) NOT NULL,
    unlocked_at         TIMESTAMP,
    CONSTRAINT uq_user_achievement_user_code
        UNIQUE (user_id, achievement_code)
);

-- New column on the existing group_post_comment table, used by the
-- "mark reply helpful" endpoint to award community XP exactly once
-- per comment.
ALTER TABLE group_post_comment
    ADD COLUMN IF NOT EXISTS marked_helpful BOOLEAN NOT NULL DEFAULT FALSE;

-- ============================================================
-- Nothing to change on xp_event - its schema (including the
-- (user_id, event_type, related_id) unique constraint) already
-- supports the new event_type values used by this chunk:
--   document_studied, quiz_completed, flashcards_completed,
--   streak_milestone, community_helpful_reply
-- ============================================================
