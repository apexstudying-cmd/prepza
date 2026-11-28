"""Organisation, opportunity and ambassador/referral ORM models."""
from datetime import datetime

from extensions import db


class Organisation(db.Model):
    """
    An employer/institution/sponsor account that can submit and manage
    its own Opportunities. Verification is admin-gated - an unverified
    organisation can still be created and staffed (OrganisationMember),
    but its opportunities cannot be published until the org itself is
    verified (enforced in the routes patch, not here).
    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.String(1000), nullable=True)
    website = db.Column(db.String(500), nullable=True)
    logo_url = db.Column(db.String(500), nullable=True)
    contact_email = db.Column(db.String(120), nullable=False)
    contact_phone = db.Column(db.String(20), nullable=True)
    verification_status = db.Column(db.String(20), nullable=False, default="pending")
    # pending -> verified | rejected
    verification_notes = db.Column(db.String(500), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    # Admin kill-switch - deactivating an org hides all its opportunities
    # without deleting anything, same soft-disable pattern as
    # University.is_active / Program.is_active elsewhere in this file.
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OrganisationMember(db.Model):
    """
    A User's membership/role within an Organisation - same shape as
    GroupMember. 'owner' is the org's primary account holder (set on
    creation, cannot be removed without transferring ownership first,
    mirrored after the sole-admin protections on GroupMember); 'manager'
    can submit/edit opportunities but not manage other staff or billing.
    """
    id = db.Column(db.Integer, primary_key=True)
    organisation_id = db.Column(db.Integer, db.ForeignKey("organisation.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="manager")
    # owner | manager
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint("organisation_id", "user_id", name="uq_org_member_org_user"),
    )


OPPORTUNITY_TYPES = ("job", "internship", "scholarship", "competition", "volunteering", "event", "other")
OPPORTUNITY_STATUSES = (
    "draft", "pending_review", "approved", "rejected",
    "published", "expired", "archived", "removed",
)


class Opportunity(db.Model):
    """
    Full lifecycle: draft -> pending_review -> approved/rejected ->
    published -> expired -> archived/removed. Expiry is computed
    server-side off expiry_date (see is_opportunity_expired() /
    the expiry sweep in the routes patch) - never trust a frontend
    clock for this, per the MVP spec.
    """
    id = db.Column(db.Integer, primary_key=True)
    organisation_id = db.Column(db.Integer, db.ForeignKey("organisation.id", ondelete="CASCADE"), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    # the OrganisationMember (by user_id) who submitted this - kept even
    # if that member later leaves the org, same pattern as
    # LibraryPublication.user_id.
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    opportunity_type = db.Column(db.String(20), nullable=False)
    location = db.Column(db.String(200), nullable=True)
    is_remote = db.Column(db.Boolean, nullable=False, default=False)
    application_url = db.Column(db.String(500), nullable=True)
    application_instructions = db.Column(db.Text, nullable=True)
    application_deadline = db.Column(db.DateTime, nullable=False)
    expiry_date = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="draft")
    rejection_reason = db.Column(db.String(500), nullable=True)
    submitted_at = db.Column(db.DateTime, nullable=True)
    reviewed_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    published_at = db.Column(db.DateTime, nullable=True)
    view_count = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Ambassador(db.Model):
    """
    A user's enrollment in the referral/ambassador program (Chunk 9).
    One row per user - applying again after rejection just resets this
    same row back to 'pending' rather than creating duplicates, since
    referral_code needs to stay stable once anything has been shared
    publicly under it.
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)
    referral_code = db.Column(db.String(20), unique=True, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")
    # pending -> active | rejected ; active -> suspended -> active (admin can reinstate)
    applied_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    rejection_reason = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Referral(db.Model):
    """
    One referred signup and its progress through the funnel:
    signed_up -> verified -> activated, with paying/commission tracked
    via first_payment_id rather than a status value (a referral can be
    "activated" for months before ever converting - those aren't
    mutually exclusive states). commission_rate_applied and
    commission_amount are snapshotted at conversion time so a later
    change to the tier thresholds/percentages in SystemSetting never
    rewrites history for referrals that already converted.
    """
    id = db.Column(db.Integer, primary_key=True)
    ambassador_id = db.Column(db.Integer, db.ForeignKey("ambassador.id"), nullable=False)
    referred_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)
    referral_code_used = db.Column(db.String(20), nullable=False)
    channel = db.Column(db.String(30), nullable=True)
    # optional ?via= tag captured at signup (e.g. "whatsapp", "instagram")

    status = db.Column(db.String(20), nullable=False, default="signed_up")
    # signed_up -> verified -> activated
    verified_at = db.Column(db.DateTime, nullable=True)
    activated_at = db.Column(db.DateTime, nullable=True)

    first_payment_id = db.Column(db.Integer, db.ForeignKey("payment.id"), unique=True, nullable=True)
    first_payment_at = db.Column(db.DateTime, nullable=True)
    commission_rate_applied = db.Column(db.Integer, nullable=True)  # whole percent, e.g. 15
    commission_amount = db.Column(db.Integer, nullable=True)  # KES, snapshotted
    unlock_at = db.Column(db.DateTime, nullable=True)
    # first_payment_at + the hold period in effect at conversion time -
    # commission becomes requestable once now() >= unlock_at.

    payout_id = db.Column(db.Integer, db.ForeignKey("ambassador_payout.id"), nullable=True)
    # set once bundled into a payout request; NULL means still available.

    voided_at = db.Column(db.DateTime, nullable=True)
    void_reason = db.Column(db.String(200), nullable=True)
    # set if the qualifying payment is later refunded - only allowed
    # while payout_id is still NULL (see admin_refund_payment).

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AmbassadorPayout(db.Model):
    """
    One payout request, bundling every currently-unlocked Referral
    commission for an ambassador at request time. amount is a snapshot
    of the sum at request time - Referral rows keep their own
    commission_amount as the source of truth, this is just the total
    actually requested/approved/paid.
    """
    id = db.Column(db.Integer, primary_key=True)
    ambassador_id = db.Column(db.Integer, db.ForeignKey("ambassador.id"), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")
    # pending -> approved -> paid ; pending -> rejected (bundled referrals released)
    payout_destination = db.Column(db.String(20), nullable=False)
    # phone number for Paystack mobile money transfer
    recipient_first_name = db.Column(db.String(100), nullable=False)
    recipient_last_name = db.Column(db.String(100), nullable=False)
    # Paystack's transfer recipient payload requires a real first/last
    # name, not just a phone number - collected explicitly at request
    # time rather than split from User.display_name, since that field
    # is an optional nickname and unreliable for an actual money transfer.
    paystack_recipient_code = db.Column(db.String(100), nullable=True)
    # Paystack recipient_code from POST /transferrecipient - created
    # once per payout on first approval attempt, then reused. Paystack
    # requires a recipient to exist before a transfer can be initiated,
    # unlike Kasapay's single-call B2C.
    paystack_transfer_code = db.Column(db.String(100), nullable=True)
    # Our own reference string passed to POST /transfer - this is what
    # GET /transfer/verify/<reference> and the transfer.* webhook events
    # are keyed on. Named to mirror Payment.reference/provider_reference
    # naming from the checkout migration.
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    rejection_reason = db.Column(db.String(500), nullable=True)
    paid_at = db.Column(db.DateTime, nullable=True)


# ---------- Student orders / exact fulfillment ----------
from student_orders import register_student_orders


# ---------- Paystack (Chunk 8, migrated from Pesapal) ----------
# Docs: paystack.com/docs/payments/accept-payments /
# paystack.com/docs/api/transaction. PAYSTACK_SECRET_KEY's own prefix
# (sk_test_ vs sk_live_) determines sandbox vs live - unlike Pesapal,
# Paystack has no separate base URL per environment.
PAYSTACK_BASE_URL = "https://api.paystack.co"
SUBSCRIPTION_PLAN_DURATIONS_MONTHS = {"plus": 1, "pro": 1}
