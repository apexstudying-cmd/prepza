"""
Chunk 7 patch 1/N: models for Opportunities + Organisation portal.

Adds 4 new models right after the Notification model:
  - Organisation        (org account + verification + profile)
  - OrganisationMember  (User <-> Organisation, role-based, mirrors GroupMember)
  - Opportunity         (full lifecycle: draft -> pending_review -> approved/
                          rejected -> published -> expired -> archived -> removed)
  - OpportunityPromotion (standard/featured/sponsored - price + payment_status
                          fields are reserved here for the Payments chunk to
                          wire up real billing; pricing itself is admin-
                          configurable via SystemSetting, same pattern as
                          price_notes/price_qna)

Anchoring strategy (deliberately robust, not a literal text match):
  1. Find the line "class Notification(db.Model):" - this class's name and
     position are stable regardless of what other chunks have added
     elsewhere in the file (Pesapal/Chunk 8 code, XP/Chunk 7 code, etc).
  2. Walk forward to find where that class body ends: the next line that
     starts in column 0 with a non-whitespace character (i.e. the next
     top-level "class ", "def ", or similar statement).
  3. Insert the new models immediately before that boundary.

This avoids repeat failures from exact-text anchors breaking on invisible
whitespace/line-ending differences. Preserves the file's original line
ending style (CRLF vs LF) on write.

Safe to re-run: checks whether Organisation already exists before doing
anything.

Usage:
    cd ~/Desktop/prepza
    python chunk7_models_patch.py
"""

import re

APP_PY = "app.py"

NOTIFICATION_CLASS_LINE = "class Notification(db.Model):"

NEW_MODELS_TEMPLATE = '''

# ---------- Opportunities + Organisation portal ----------

ORGANISATION_VERIFICATION_STATUSES = ("pending", "verified", "rejected")


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


OPPORTUNITY_PROMOTION_TYPES = ("standard", "featured", "sponsored")
OPPORTUNITY_PROMOTION_APPROVAL_STATUSES = ("pending", "approved", "rejected")
OPPORTUNITY_PROMOTION_PAYMENT_STATUSES = ("unpaid", "pending", "paid", "refunded")


class OpportunityPromotion(db.Model):
    """
    One promotion campaign for an Opportunity. Deliberately separate
    from Opportunity itself (rather than fields on it) since an org can
    run more than one promotion over an opportunity's lifetime, each
    with its own window/price/approval. price is a snapshot captured at
    creation time from admin-configurable SystemSetting pricing (same
    pattern as get_content_prices()) - NOT hard-coded here. Actual
    payment collection/webhook wiring belongs to the Payments chunk;
    payment_status exists now so that schema is ready for it.
    """
    id = db.Column(db.Integer, primary_key=True)
    opportunity_id = db.Column(db.Integer, db.ForeignKey("opportunity.id", ondelete="CASCADE"), nullable=False)
    organisation_id = db.Column(db.Integer, db.ForeignKey("organisation.id"), nullable=False)
    # denormalized for admin filtering, per the MVP spec's stored-fields list
    promotion_type = db.Column(db.String(20), nullable=False)
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=False)
    price = db.Column(db.Integer, nullable=False, default=0)
    payment_status = db.Column(db.String(20), nullable=False, default="unpaid")
    approval_status = db.Column(db.String(20), nullable=False, default="pending")
    reviewed_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

'''


def find_class_end(lines, class_start_idx):
    """
    Given the index of a 'class X(db.Model):' line, walk forward and
    return the index of the first subsequent line that starts at column
    0 with a non-blank, non-whitespace character - i.e. the first line
    that is NOT part of this class's body. That's where we insert.
    """
    for i in range(class_start_idx + 1, len(lines)):
        stripped = lines[i].rstrip("\r\n")
        if stripped == "":
            continue  # blank lines are still "inside" the gap, keep scanning
        if stripped[0] not in (" ", "\t"):
            return i
    raise AssertionError("Could not find end of Notification class - reached end of file")


def main():
    with open(APP_PY, "rb") as f:
        raw = f.read()

    uses_crlf = b"\r\n" in raw
    text = raw.decode("utf-8")

    if "class Organisation(db.Model):" in text:
        print("Already applied - Organisation model found. Nothing to do.")
        return

    lines = text.splitlines(keepends=True)
    notification_line_idx = None
    for i, line in enumerate(lines):
        if line.rstrip("\r\n") == NOTIFICATION_CLASS_LINE:
            notification_line_idx = i
            break
    assert notification_line_idx is not None, (
        "Could not find 'class Notification(db.Model):' in app.py. "
        "Aborting without modifying anything."
    )

    insert_idx = find_class_end(lines, notification_line_idx)

    # Sanity: everything between Notification and the insertion point
    # should just be its own field definitions - confirm we're not
    # about to insert in the middle of something unexpected.
    tail_after_notification = "".join(lines[notification_line_idx:insert_idx])
    assert "created_at = db.Column(db.DateTime, default=datetime.utcnow)" in tail_after_notification, (
        "Notification class body looked different than expected - aborting "
        "without modifying anything. Boundary found at line "
        f"{insert_idx + 1}: {lines[insert_idx].rstrip()!r}"
    )

    new_block = NEW_MODELS_TEMPLATE
    if uses_crlf:
        new_block = new_block.replace("\n", "\r\n")

    lines.insert(insert_idx, new_block)
    new_text = "".join(lines)

    assert "class Opportunity(db.Model):" in new_text
    assert "class OrganisationMember(db.Model):" in new_text
    assert "class OpportunityPromotion(db.Model):" in new_text

    with open(APP_PY, "wb") as f:
        f.write(new_text.encode("utf-8"))

    print("Patched app.py: added Organisation, OrganisationMember, Opportunity, OpportunityPromotion.")
    print(f"Inserted right after the Notification class (was line {notification_line_idx + 1} "
          f"in the original file).")
    print("Next: run create_chunk7_tables.py to create the 4 new tables.")


if __name__ == "__main__":
    main()
