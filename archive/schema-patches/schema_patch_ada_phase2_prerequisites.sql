-- Ada Phase 2 - Diagnostic Teaching foundation (prerequisite graph)
-- Run manually in the Supabase SQL editor. Depends on "learning_concept"
-- already existing (Ada Phase 1's schema_patch_ada_phase1.sql).

CREATE TABLE IF NOT EXISTS concept_prerequisite (
    id SERIAL PRIMARY KEY,
    concept_id INTEGER NOT NULL REFERENCES learning_concept(id),
    prerequisite_concept_id INTEGER NOT NULL REFERENCES learning_concept(id),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_concept_prerequisite_pair UNIQUE (concept_id, prerequisite_concept_id)
);

CREATE INDEX IF NOT EXISTS ix_concept_prerequisite_concept ON concept_prerequisite(concept_id);
