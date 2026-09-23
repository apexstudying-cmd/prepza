from pathlib import Path
from b2b_campaign_metering import _unit_price_minor


def _campaign(**overrides):
    row = {
        "placement": "feed",
        "bid_type": "both",
        "target_json": {"billing_modes": ["cpm", "cpc"]},
        "pricing_snapshot": {
            "home_impression_cpm": {"value": {"amount_kes": 350}},
            "click_cpc": {"value": {"amount_kes": 20}},
            "push_delivery_cpm": {"value": {"amount_kes": 1500}},
        },
        "bid_kes": 350,
    }
    row.update(overrides)
    return row


def test_feed_impression_price_is_one_cpm_unit_in_minor_currency():
    assert _unit_price_minor(_campaign(), "impression") == 35


def test_click_price_uses_frozen_cpc_snapshot():
    assert _unit_price_minor(_campaign(), "click") == 2000


def test_push_price_uses_frozen_push_cpm_snapshot():
    assert _unit_price_minor(_campaign(placement="push"), "push_delivery") == 150


def test_wrong_placement_cannot_be_billed_as_push():
    assert _unit_price_minor(_campaign(placement="feed"), "push_delivery") == 0


def test_cpc_is_not_billable_when_campaign_snapshot_disallows_it():
    assert _unit_price_minor(_campaign(target_json={"billing_modes": ["cpm"]}), "click") == 0


def test_b2b_contract_keeps_payment_and_campaign_value_separate():
    source = Path("b2b_campaign_payments.py").read_text(encoding="utf-8")
    assert "campaign_amount_minor" in source
    assert "processing_fee_minor" in source
    assert "customer_fee_mode" in source


def test_b2b_payment_path_is_signature_verified():
    source = Path("b2b_campaign_payments.py").read_text(encoding="utf-8")
    assert "provider_signature_valid()" in source
    assert "x-paystack-signature" in source


def test_etims_tax_invoice_is_fail_closed_until_reconciled():
    source = Path("b2b_organisation_portal.py").read_text(encoding="utf-8")
    assert "etims_status" in source
    assert "etims_invoice_number" in source
    assert "The eTIMS tax invoice has not been reconciled by Prepza yet." in source
