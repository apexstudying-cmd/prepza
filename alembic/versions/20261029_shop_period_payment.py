"""Record the payment that fulfilled each Shop listing period.

Revision ID: 20261029_shop_period_payment
Revises: 20261028_shop_listing_expiry
"""
from alembic import op
import sqlalchemy as sa

revision = "20261029_shop_period_payment"
down_revision = "20261028_shop_listing_expiry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("shop_listing", sa.Column("posting_period_payment_reference", sa.String(length=50), nullable=True), schema="public")
    op.create_unique_constraint("uq_shop_listing_period_payment_reference", "shop_listing", ["posting_period_payment_reference"], schema="public")


def downgrade() -> None:
    op.drop_constraint("uq_shop_listing_period_payment_reference", "shop_listing", schema="public", type_="unique")
    op.drop_column("shop_listing", "posting_period_payment_reference", schema="public")
