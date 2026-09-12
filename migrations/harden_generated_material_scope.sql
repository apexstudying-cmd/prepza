-- GeneratedMaterial is the application-facing projection of a canonical AI artifact.
-- Shared material has no owner; private material is owner-scoped.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_generated_material_scope'
          AND conrelid = 'generated_material'::regclass
    ) THEN
        ALTER TABLE generated_material
            ADD CONSTRAINT ck_generated_material_scope
            CHECK (scope IN ('shared', 'private'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_generated_material_scope_owner'
          AND conrelid = 'generated_material'::regclass
    ) THEN
        ALTER TABLE generated_material
            ADD CONSTRAINT ck_generated_material_scope_owner
            CHECK (
                (scope = 'shared' AND owner_user_id IS NULL)
                OR
                (scope = 'private' AND owner_user_id IS NOT NULL)
            );
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_generated_material_scope_owner
    ON generated_material (scope, owner_user_id);
