"""Contract tests for Prepza Shop pricing and seller-contact validation.

These pure tests intentionally avoid importing app.py so they run quickly
without a PostgreSQL service or any provider credentials.
"""
import pytest

from shop_marketplace import (
    LISTING_POST_FEE_KES,
    listing_fee_for_post_number,
    normalize_whatsapp_number,
    validate_listing_payload,
)


def test_first_listing_is_free_and_each_later_post_costs_kes_100():
    assert listing_fee_for_post_number(1) == 0
    assert listing_fee_for_post_number(2) == LISTING_POST_FEE_KES == 100
    assert listing_fee_for_post_number(3) == 100


@pytest.mark.parametrize("value,expected", [
    ("0712345678", "254712345678"),
    ("+254712345678", "254712345678"),
    ("254712345678", "254712345678"),
])
def test_whatsapp_number_is_normalized_to_international_digits(value, expected):
    assert normalize_whatsapp_number(value) == expected


@pytest.mark.parametrize("value", ["", "07123", "1234567890", "https://wa.me/254712345678", "+1 2025550100"])
def test_invalid_or_non_kenyan_whatsapp_contact_is_rejected(value):
    with pytest.raises(ValueError):
        normalize_whatsapp_number(value)


def test_listing_payload_trims_text_and_accepts_expected_fields():
    result = validate_listing_payload({
        "title": "  Scientific Calculator  ",
        "description": "  Casio calculator in good condition.  ",
        "category": "Electronics",
        "condition": "good",
        "price_kes": 1200,
        "location_area": "Kahawa, near campus",
        "whatsapp_number": "0712345678",
    })
    assert result["title"] == "Scientific Calculator"
    assert result["description"] == "Casio calculator in good condition."
    assert result["price_kes"] == 1200
    assert result["whatsapp_number"] == "254712345678"


@pytest.mark.parametrize("payload", [
    {"title": "", "description": "x", "category": "Books", "condition": "new", "price_kes": 100},
    {"title": "Phone", "description": "x", "category": "Books", "condition": "new", "price_kes": -1},
    {"title": "Phone", "description": "x", "category": "Books", "condition": "new", "price_kes": 1.5},
    {"title": "Phone", "description": "x", "category": "Books", "condition": "broken", "price_kes": 100},
])
def test_invalid_listing_payload_is_rejected(payload):
    with pytest.raises(ValueError):
        validate_listing_payload(payload)
