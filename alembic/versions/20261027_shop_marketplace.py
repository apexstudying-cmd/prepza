"""Add the Prepza Shop classifieds MVP.

Revision ID: 20261027_shop_marketplace
Revises: 20261007_doc_material
"""
from alembic import op
import sqlalchemy as sa

revision = "20261027_shop_marketplace"
down_revision = "20261007_doc_material"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shop_listing",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("seller_id", sa.Integer(), sa.ForeignKey("public.user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("condition", sa.String(length=20), nullable=False),
        sa.Column("price_kes", sa.Integer(), nullable=False),
        sa.Column("location_area", sa.String(length=100), nullable=False),
        sa.Column("whatsapp_number", sa.String(length=12), nullable=True),
        sa.Column("image_keys", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="draft"),
        sa.Column("is_free_post", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("posting_fee_kes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("posting_fee_paid", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("posting_payment_reference", sa.String(length=50), nullable=True, unique=True),
        sa.Column("checkout_url", sa.String(length=500), nullable=True),
        sa.Column("moderation_note", sa.String(length=500), nullable=True),
        sa.Column("moderated_by", sa.Integer(), sa.ForeignKey("public.user.id"), nullable=True),
        sa.Column("moderated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("sold_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("price_kes >= 0", name="ck_shop_listing_price_nonnegative"),
        sa.CheckConstraint("posting_fee_kes IN (0, 100)", name="ck_shop_listing_posting_fee"),
        schema="public",
    )
    op.create_index("ix_shop_listing_seller_id", "shop_listing", ["seller_id"], schema="public")
    op.create_index("ix_shop_listing_category", "shop_listing", ["category"], schema="public")
    op.create_index("ix_shop_listing_location_area", "shop_listing", ["location_area"], schema="public")
    op.create_index("ix_shop_listing_status", "shop_listing", ["status"], schema="public")
    op.create_index("ix_shop_listing_created_at", "shop_listing", ["created_at"], schema="public")
    op.create_index("ix_shop_listing_active_created", "shop_listing", ["status", "created_at"], schema="public")

    op.create_table(
        "shop_saved_listing",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("public.user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("listing_id", sa.Integer(), sa.ForeignKey("public.shop_listing.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "listing_id", name="uq_shop_saved_user_listing"),
        schema="public",
    )
    op.create_index("ix_shop_saved_listing_user_id", "shop_saved_listing", ["user_id"], schema="public")
    op.create_index("ix_shop_saved_listing_listing_id", "shop_saved_listing", ["listing_id"], schema="public")

    op.create_table(
        "shop_report",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("listing_id", sa.Integer(), sa.ForeignKey("public.shop_listing.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reporter_id", sa.Integer(), sa.ForeignKey("public.user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reason", sa.String(length=40), nullable=False),
        sa.Column("details", sa.String(length=1000), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("public.user.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("listing_id", "reporter_id", name="uq_shop_report_listing_reporter"),
        schema="public",
    )
    op.create_index("ix_shop_report_listing_id", "shop_report", ["listing_id"], schema="public")
    op.create_index("ix_shop_report_status", "shop_report", ["status"], schema="public")


def downgrade() -> None:
    op.drop_table("shop_report", schema="public")
    op.drop_table("shop_saved_listing", schema="public")
    op.drop_table("shop_listing", schema="public")
