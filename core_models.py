"""Commerce and legacy content-progress ORM models."""
from datetime import datetime

from extensions import db


class ContentItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    content_type = db.Column(db.String(20), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    file_url = db.Column(db.String(500), nullable=True)
    paper_year = db.Column(db.Integer, nullable=True)
    is_downloadable = db.Column(db.Boolean, default=True)
    price = db.Column(db.Integer, default=0)


class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    content_item_id = db.Column(db.Integer, db.ForeignKey("content_item.id"), nullable=True)
    phone_number = db.Column(db.String(20), nullable=True)
    amount = db.Column(db.Integer, nullable=False)
    # Unused since the Daraja -> Pesapal swap (Chunk 8). Left in place
    # rather than dropped, per the no-destructive-migrations convention.
    checkout_request_id = db.Column(db.String(100), unique=True, nullable=True)
    status = db.Column(db.String(20), default="pending")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # ---- Paystack (Chunk 8, migrated from Pesapal) ----
    provider = db.Column(db.String(20), nullable=False, default="paystack")
    reference = db.Column(db.String(50), unique=True, nullable=True)
    # Reference WE generate and pass to Paystack on initialize - this is
    # what Paystack's webhook/callback hand back to us, and what
    # /transaction/verify/<reference> is keyed on. Renamed from
    # merchant_reference (Pesapal-specific naming).
    provider_reference = db.Column(db.String(100), unique=True, nullable=True)
    # Paystack's own internal transaction id (the "id" field from a
    # verify-transaction response), stored for support/audit lookups in
    # the Paystack dashboard. Renamed from order_tracking_id.

    # 'content' (one-off document/item purchase) or 'subscription' (plan purchase)
    payment_type = db.Column(db.String(20), nullable=False, default="content")
    plan = db.Column(db.String(20), nullable=True)  # 'plus' | 'pro' - subscription only
    subscription_starts_at = db.Column(db.DateTime, nullable=True)  # subscription entitlement period start
    subscription_expires_at = db.Column(db.DateTime, nullable=True)  # subscription only
    # Immutable feature allowance snapshot for refund/accounting calculations.
    subscription_allowance_snapshot = db.Column(db.JSON, nullable=True)


class SystemSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=False, default="")


class ViewProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    content_item_id = db.Column(db.Integer, db.ForeignKey("content_item.id"), nullable=False)
    page_num = db.Column(db.Integer, default=0)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint("user_id", "content_item_id", name="uq_view_progress_user_item"),
    )
