from decimal import Decimal

from ai_economics import (
    sync_paystack_recurring_plan,
    ADA_UNIT_WEIGHTS,
    PLAN_DEFAULTS,
    calculate_ada_units,
    validate_plan_patch,
)


def test_ada_unit_weights_are_locked():
    assert ADA_UNIT_WEIGHTS["normal_input"] == Decimal("1")
    assert ADA_UNIT_WEIGHTS["cache_write"] == Decimal("1.25")
    assert ADA_UNIT_WEIGHTS["cached_input"] == Decimal("0.1")
    assert ADA_UNIT_WEIGHTS["output"] == Decimal("6")


def test_ada_units_round_up():
    assert calculate_ada_units(
        input_tokens=1000,
        cached_tokens=500,
        cache_write_tokens=200,
        output_tokens=100,
    ) == 1900


def test_plan_defaults_match_locked_entitlements():
    assert PLAN_DEFAULTS["free"]["ada_monthly_units"] == 500_000
    assert PLAN_DEFAULTS["plus"]["ada_monthly_units"] == 2_500_000
    assert PLAN_DEFAULTS["pro"]["ada_monthly_units"] == 6_000_000
    assert PLAN_DEFAULTS["plus"]["price_kes"] == 499
    assert PLAN_DEFAULTS["pro"]["price_kes"] == 999
    assert PLAN_DEFAULTS["free"]["podcast_minutes"] == 10
    assert PLAN_DEFAULTS["plus"]["podcast_minutes"] == 120
    assert PLAN_DEFAULTS["pro"]["podcast_minutes"] == 350


def test_plan_patch_rejects_unknown_fields():
    cleaned, errors = validate_plan_patch({"ada_monthly_units": 123, "student_tokens": 999})
    assert cleaned["ada_monthly_units"] == 123
    assert "student_tokens" in errors


def test_plan_patch_rejects_negative_limits():
    cleaned, errors = validate_plan_patch({"questions": -1})
    assert cleaned == {}
    assert "questions" in errors


def test_plan_patch_accepts_feature_and_access_flags():
    cleaned, errors = validate_plan_patch({
        "summary_pages": 25,
        "offline_study": True,
        "premium_library": True,
        "study_hub_uploads": True,
    })
    assert not errors
    assert cleaned == {
        "summary_pages": 25,
        "offline_study": True,
        "premium_library": True,
        "study_hub_uploads": True,
    }


def test_offline_study_is_core_for_free():
    assert PLAN_DEFAULTS["free"]["offline_study"] is True


def test_admin_cannot_disable_offline_study():
    cleaned, errors = validate_plan_patch({"offline_study": False})
    assert cleaned == {}
    assert errors["offline_study"] == "offline_study is always enabled for all students"



def test_paystack_plan_sync_updates_provider_when_price_drifts(monkeypatch):
    calls = []
    monkeypatch.setenv("PAYSTACK_PLUS_PLAN_CODE", "PLN_plus")

    def fake_request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        if method == "GET":
            return {"status": True, "data": {"amount": 49900, "currency": "KES", "interval": "monthly"}}
        return {"status": True, "message": "Plan updated. 2 subscription(s) affected"}

    import sys
    from types import SimpleNamespace
    monkeypatch.setitem(sys.modules, "app", SimpleNamespace(paystack_request=fake_request))
    result = sync_paystack_recurring_plan("plus", {"display_name": "Plus", "price_kes": 599})
    assert result["status"] == "synchronized"
    assert result["amount_kes"] == 599
    assert calls[1][0] == "PUT"
    assert calls[1][1] == "/plan/PLN_plus"
    assert calls[1][2]["json"]["amount"] == 59900
    assert calls[1][2]["json"]["currency"] == "KES"
    assert calls[1][2]["json"]["interval"] == "monthly"
    assert calls[1][2]["json"]["update_existing_subscriptions"] is True


def test_paystack_plan_sync_does_not_write_when_already_matching(monkeypatch):
    calls = []
    monkeypatch.setenv("PAYSTACK_PRO_PLAN_CODE", "PLN_pro")

    def fake_request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return {"status": True, "data": {"amount": 99900, "currency": "KES", "interval": "monthly"}}

    import app
    monkeypatch.setattr(app, "paystack_request", fake_request)
    result = sync_paystack_recurring_plan("pro", {"display_name": "Pro", "price_kes": 999})
    assert result["status"] == "already_synchronized"
    assert len(calls) == 1


def test_paystack_plan_sync_requires_plan_code(monkeypatch):
    monkeypatch.delenv("PAYSTACK_PLUS_PLAN_CODE", raising=False)
    import pytest
    with pytest.raises(RuntimeError, match="PAYSTACK_PLUS_PLAN_CODE"):
        sync_paystack_recurring_plan("plus", {"price_kes": 599})
