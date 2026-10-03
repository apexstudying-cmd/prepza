"""Add the opportunity academic targeting tables required by the current runtime."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20261003_opportunity_targeting"
down_revision = "20261002_user_model"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "opportunity_university_target",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "opportunity_id",
            sa.Integer(),
            sa.ForeignKey("opportunity.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "university_id",
            sa.Integer(),
            sa.ForeignKey("university.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "opportunity_id",
            "university_id",
            name="uq_opp_university_target",
        ),
        schema="public",
    )

    op.create_index(
        "ix_opp_university_target_university",
        "opportunity_university_target",
        ["university_id"],
        schema="public",
    )

    op.create_table(
        "opportunity_program_target",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "opportunity_id",
            sa.Integer(),
            sa.ForeignKey("opportunity.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "program_id",
            sa.Integer(),
            sa.ForeignKey("program.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "opportunity_id",
            "program_id",
            name="uq_opp_program_target",
        ),
        schema="public",
    )

    op.create_index(
        "ix_opp_program_target_program",
        "opportunity_program_target",
        ["program_id"],
        schema="public",
    )

    op.create_table(
        "opportunity_year_target",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "opportunity_id",
            sa.Integer(),
            sa.ForeignKey("opportunity.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.UniqueConstraint(
            "opportunity_id",
            "year",
            name="uq_opp_year_target",
        ),
        schema="public",
    )

    op.create_index(
        "ix_opp_year_target_year",
        "opportunity_year_target",
        ["year"],
        schema="public",
    )

    op.create_table(
        "opportunity_semester_target",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "opportunity_id",
            sa.Integer(),
            sa.ForeignKey("opportunity.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("semester", sa.Integer(), nullable=False),
        sa.UniqueConstraint(
            "opportunity_id",
            "semester",
            name="uq_opp_semester_target",
        ),
        schema="public",
    )

    op.create_index(
        "ix_opp_semester_target_semester",
        "opportunity_semester_target",
        ["semester"],
        schema="public",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_opp_semester_target_semester",
        table_name="opportunity_semester_target",
        schema="public",
    )
    op.drop_table("opportunity_semester_target", schema="public")

    op.drop_index(
        "ix_opp_year_target_year",
        table_name="opportunity_year_target",
        schema="public",
    )
    op.drop_table("opportunity_year_target", schema="public")

    op.drop_index(
        "ix_opp_program_target_program",
        table_name="opportunity_program_target",
        schema="public",
    )
    op.drop_table("opportunity_program_target", schema="public")

    op.drop_index(
        "ix_opp_university_target_university",
        table_name="opportunity_university_target",
        schema="public",
    )
    op.drop_table("opportunity_university_target", schema="public")
