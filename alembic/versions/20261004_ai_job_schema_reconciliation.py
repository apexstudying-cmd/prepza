"""Reconcile ai_job columns used by the current runtime.

The verified baseline predates later AI job ownership and generation
configuration fields. Keep user_id nullable so legacy extraction jobs remain
valid while current student generation jobs can record their owner.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20261004_ai_job_reconcile"
down_revision = "20261003_opportunity_targeting"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_job",
        sa.Column("user_id", sa.Integer(), nullable=True),
        schema="public",
    )
    op.create_index(
        "ix_ai_job_user_id",
        "ai_job",
        ["user_id"],
        schema="public",
    )
    op.create_foreign_key(
        "ai_job_user_id_fkey",
        "ai_job",
        "user",
        ["user_id"],
        ["id"],
        source_schema="public",
        referent_schema="public",
    )

    op.add_column(
        "ai_job",
        sa.Column(
            "generation_parameters",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        schema="public",
    )


def downgrade() -> None:
    op.drop_column(
        "ai_job",
        "generation_parameters",
        schema="public",
    )
    op.drop_constraint(
        "ai_job_user_id_fkey",
        "ai_job",
        type_="foreignkey",
        schema="public",
    )
    op.drop_index(
        "ix_ai_job_user_id",
        table_name="ai_job",
        schema="public",
    )
    op.drop_column(
        "ai_job",
        "user_id",
        schema="public",
    )
