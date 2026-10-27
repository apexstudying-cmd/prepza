"""Add 30-day expiry to paid Shop listing periods.

Revision ID: 20261028_shop_listing_expiry
Revises: 20261027_shop_marketplace
"""
from alembic import op
import sqlalchemy as sa

revision = "20261028_shop_listing_expiry"
down_revision = "20261027_shop_marketplace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("shop_listing", sa.Column("posting_fee_expires_at", sa.DateTime(), nullable=True), schema="public")
    op.create_index("ix_shop_listing_posting_fee_expires_at", "shop_listing", ["posting_fee_expires_at"], schema="public")
    # Existing listings that were already paid receive one transition period;
    # this avoids unexpectedly hiding current sellers during deployment.
    op.execute("UPDATE public.shop_listing SET posting_fee_expires_at = now() + interval '30 days' WHERE posting_fee_paid = true AND posting_fee_expires_at IS NULL")


def downgrade() -> None:
    op.drop_index("ix_shop_listing_posting_fee_expires_at", table_name="shop_listing", schema="public")
    op.drop_column("shop_listing", "posting_fee_expires_at", schema="public")
