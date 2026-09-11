-- Fingerprinted AI artifact identity.
-- Run after the existing GeneratedMaterial table has been created.
-- Existing artifacts receive a deterministic legacy fingerprint so they remain
-- reusable after the uniqueness model changes.

ALTER TABLE generated_material
    ADD COLUMN IF NOT EXISTS generation_fingerprint VARCHAR(128),
    ADD COLUMN IF NOT EXISTS generation_parameters JSONB,
    ADD COLUMN IF NOT EXISTS generation_version VARCHAR(50) NOT NULL DEFAULT 'v1',
    ADD COLUMN IF NOT EXISTS scope VARCHAR(20) NOT NULL DEFAULT 'shared',
    ADD COLUMN IF NOT EXISTS owner_user_id INTEGER;

UPDATE generated_material
SET generation_fingerprint = md5(
    'legacy:v1:' || document_content_id::text || ':' || material_type
)
WHERE generation_fingerprint IS NULL;

ALTER TABLE generated_material
    ALTER COLUMN generation_fingerprint SET NOT NULL;

ALTER TABLE generated_material
    DROP CONSTRAINT IF EXISTS uq_material_content_type;

CREATE UNIQUE INDEX IF NOT EXISTS uq_generated_material_fingerprint
    ON generated_material (generation_fingerprint);

CREATE INDEX IF NOT EXISTS ix_generated_material_content_type
    ON generated_material (document_content_id, material_type);

CREATE INDEX IF NOT EXISTS ix_generated_material_owner
    ON generated_material (owner_user_id);
