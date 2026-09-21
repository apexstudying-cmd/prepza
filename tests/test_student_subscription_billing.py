import datetime as dt
from decimal import Decimal

import student_subscription_billing as billing


def _payment(amount=499):
    return {
        "id": 1,
        "amount": amount,
        "plan": "plus",
        "created_at": dt.datetime.utcnow(),
    }


def test_refund_policy_weights_sum_to_100_percent():
    assert sum(billing.FEATURE_WEIGHTS.values()) == Decimal("1.00")


def test_zero_usage_within_24_hours_is_full_refund(monkeypatch):
    monkeypatch.setattr(billing, "_policy", lambda db: (24, Decimal("20"), True))
    monkeypatch.setattr(
        billing,
        "_consumption_breakdown",
        lambda db, payment: {"consumed_value_kes": 0, "features": {}},
    )
    quote = billing.calculate_refund_quote(None, _payment(), dt.datetime.utcnow())
    assert quote["eligible_standard"] is True
    assert quote["refund_amount_kes"] == 499
    assert quote["retention_amount_kes"] == 0


def test_consumed_subscription_keeps_published_retention(monkeypatch):
    monkeypatch.setattr(billing, "_policy", lambda db: (24, Decimal("20"), True))
    monkeypatch.setattr(
        billing,
        "_consumption_breakdown",
        lambda db, payment: {"consumed_value_kes": 100, "features": {}},
    )
    quote = billing.calculate_refund_quote(None, _payment(), dt.datetime.utcnow())
    assert quote["eligible_standard"] is True
    assert quote["consumed_value_kes"] == 100
    assert quote["retention_amount_kes"] == 100
    assert quote["refund_amount_kes"] == 299


def test_refund_after_standard_window_is_not_standard_eligible(monkeypatch):
    monkeypatch.setattr(billing, "_policy", lambda db: (24, Decimal("20"), True))
    monkeypatch.setattr(
        billing,
        "_consumption_breakdown",
        lambda db, payment: {"consumed_value_kes": 0, "features": {}},
    )
    old = dt.datetime.utcnow() - dt.timedelta(hours=25)
    quote = billing.calculate_refund_quote(None, _payment(), dt.datetime.utcnow())
    # Replace the payment creation timestamp with an actually old one.
    quote = billing.calculate_refund_quote(
        None, {**_payment(), "created_at": old}, dt.datetime.utcnow()
    )
    assert quote["within_window"] is False
    assert quote["eligible_standard"] is False
    assert quote["refund_amount_kes"] == 0
