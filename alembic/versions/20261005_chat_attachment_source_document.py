"""Reconcile the chat attachment source-document column used by MessageAttachment."""
from __future__ import annotations

from alembic import op


revision = "20261005_chat_attachment_source_document"
down_revision = "20261004_ai_job_reconcile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The historical SQL migration predates the Alembic-managed QA path.
    # Keep this idempotent so fresh baseline databases and existing databases
    # converge on the same ORM-visible schema.
    op.execute(
        """
        ALTER TABLE public.message_attachment
        ADD COLUMN IF NOT EXISTS source_document_content_id INTEGER
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'message_attachment_source_document_content_id_fkey'
            ) THEN
                ALTER TABLE public.message_attachment
                ADD CONSTRAINT message_attachment_source_document_content_id_fkey
                FOREIGN KEY (source_document_content_id)
                REFERENCES public.document_content(id);
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_message_attachment_source_document_content
        ON public.message_attachment(source_document_content_id)
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS public.ix_message_attachment_source_document_content"
    )
    op.execute(
        """
        ALTER TABLE public.message_attachment
        DROP CONSTRAINT IF EXISTS message_attachment_source_document_content_id_fkey
        """
    )
    op.execute(
        """
        ALTER TABLE public.message_attachment
        DROP COLUMN IF EXISTS source_document_content_id
        """
    )
