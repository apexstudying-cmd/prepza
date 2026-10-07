"""Reconcile the DocumentContent -> GeneratedMaterial ORM link.

The current runtime exposes DocumentContent.material_id so the deduplicated
document-content record can point at its reusable generated study material.
The verified baseline predates that nullable relationship.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20261007_document_content_material"
down_revision = "20261005_chat_attach_source_doc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_content",
        sa.Column("material_id", sa.Integer(), nullable=True),
        schema="public",
        if_not_exists=True,
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'document_content_material_id_fkey'
            ) THEN
                ALTER TABLE public.document_content
                ADD CONSTRAINT document_content_material_id_fkey
                FOREIGN KEY (material_id)
                REFERENCES public.generated_material(id);
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.drop_constraint(
        "document_content_material_id_fkey",
        "document_content",
        type_="foreignkey",
        schema="public",
    )
    op.drop_column(
        "document_content",
        "material_id",
        schema="public",
    )
