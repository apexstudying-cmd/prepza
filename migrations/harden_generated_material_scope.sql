-- GeneratedMaterial is the application-facing projection of a canonical AI artifact.
-- Shared material has no owner; private material is owner-scoped.

ALTER TABLE generated_material
    ADD CONSTRAINT ck_generated_material_scope
    CHECK (scope IN ('shared', 'private'));

ALTER TABLE generated_material
    ADD CONSTRAINT ck_generated_material_scope_owner
    CHECK (
        (scope = 'shared' AND owner_user_id IS NULL)
        OR
        (scope = 'private' AND owner_user_id IS NOT NULL)
    );

CREATE INDEX IF NOT EXISTS ix_generated_material_scope_owner
    ON generated_material (scope, owner_user_id);
