-- Ada Phase 2 - Concept Mastery
-- Run manually in the Supabase SQL editor (no migrations tooling in this
-- codebase). Depends on "user" and "learning_concept" already existing
-- (both landed in Ada Phase 1's schema_patch_ada_phase1.sql) - run this
-- AFTER that one if you're setting up a fresh database.

CREATE TABLE IF NOT EXISTS student_concept_mastery (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES "user"(id),
    concept_id INTEGER NOT NULL REFERENCES learning_concept(id),
    mastery_score INTEGER NOT NULL DEFAULT 0,
    confidence VARCHAR(20) NOT NULL DEFAULT 'low',
    exposure_count INTEGER NOT NULL DEFAULT 0,
    misconception_count INTEGER NOT NULL DEFAULT 0,
    last_practiced_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_concept_mastery_user_concept UNIQUE (user_id, concept_id)
);

CREATE INDEX IF NOT EXISTS ix_concept_mastery_user ON student_concept_mastery(user_id);
