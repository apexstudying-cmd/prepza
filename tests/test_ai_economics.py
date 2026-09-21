from decimal import Decimal

from ai_economics import (
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
    ) == 3150


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
