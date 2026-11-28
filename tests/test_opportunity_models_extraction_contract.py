from __future__ import annotations

from pathlib import Path

from opportunity_models import (
    Ambassador, AmbassadorPayout, Opportunity, Organisation,
    OrganisationMember, Referral, OPPORTUNITY_STATUSES, OPPORTUNITY_TYPES,
)

ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")


def test_opportunity_and_referral_models_are_domain_owned_and_legacy_exported() -> None:
    assert "from opportunity_models import (" in APP_SOURCE
    for name in ("Organisation", "OrganisationMember", "Opportunity", "Ambassador", "Referral", "AmbassadorPayout"):
        assert f"class {name}(db.Model)" not in APP_SOURCE
        assert name in APP_SOURCE


def test_opportunity_domain_table_and_column_contracts_are_preserved() -> None:
    expected = (
        (Organisation, "organisation", {"id", "name", "description", "website", "logo_url", "contact_email", "contact_phone", "verification_status", "verification_notes", "is_active", "created_by", "created_at", "updated_at"}),
        (OrganisationMember, "organisation_member", {"id", "organisation_id", "user_id", "role", "joined_at"}),
        (Opportunity, "opportunity", {"id", "organisation_id", "created_by", "title", "description", "opportunity_type", "location", "is_remote", "application_url", "application_instructions", "application_deadline", "expiry_date", "status", "rejection_reason", "submitted_at", "reviewed_by", "reviewed_at", "published_at", "view_count", "created_at", "updated_at"}),
        (Ambassador, "ambassador", {"id", "user_id", "referral_code", "status", "applied_at", "reviewed_by", "reviewed_at", "rejection_reason", "created_at", "updated_at"}),
        (Referral, "referral", {"id", "ambassador_id", "referred_user_id", "referral_code_used", "channel", "status", "verified_at", "activated_at", "first_payment_id", "first_payment_at", "commission_rate_applied", "commission_amount", "unlock_at", "payout_id", "voided_at", "void_reason", "created_at", "updated_at"}),
        (AmbassadorPayout, "ambassador_payout", {"id", "ambassador_id", "amount", "status", "payout_destination", "recipient_first_name", "recipient_last_name", "paystack_recipient_code", "paystack_transfer_code", "requested_at", "reviewed_by", "reviewed_at", "rejection_reason", "paid_at"}),
    )
    for model, table, columns in expected:
        assert model.__tablename__ == table
        assert set(model.__table__.columns.keys()) == columns


def test_opportunity_lifecycle_and_referral_constraints_are_preserved() -> None:
    assert OPPORTUNITY_TYPES == ("job", "internship", "scholarship", "competition", "volunteering", "event", "other")
    assert OPPORTUNITY_STATUSES == ("draft", "pending_review", "approved", "rejected", "published", "expired", "archived", "removed")
    for model, name in (
        (OrganisationMember, "uq_org_member_org_user"),
        (Ambassador, None),
        (Referral, None),
    ):
        if name:
            assert any(getattr(c, "name", None) == name for c in model.__table__.constraints)
    assert next(iter(OrganisationMember.__table__.c.organisation_id.foreign_keys)).target_fullname == "organisation.id"
    assert next(iter(Referral.__table__.c.first_payment_id.foreign_keys)).target_fullname == "payment.id"
