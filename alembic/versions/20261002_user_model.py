"""Reconcile the verified Supabase baseline with the current main User model."""
from alembic import op
import sqlalchemy as sa

revision = "20261002_user_model"
down_revision = "20261002_baseline"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column(
        "user",
        sa.Column("avatar_storage_path", sa.String(length=500), nullable=True),
        schema="public",
        if_not_exists=True,
    )
    op.add_column(
        "user",
        sa.Column("read_receipts_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        schema="public",
        if_not_exists=True,
    )

def downgrade() -> None:
    op.drop_column("user", "read_receipts_enabled", schema="public", if_exists=True)
    op.drop_column("user", "avatar_storage_path", schema="public", if_exists=True)
