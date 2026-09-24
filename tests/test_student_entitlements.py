"""Student entitlement and exact-output contract tests."""
from usage_billing import ADA_TOKEN_LIMITS, STUDENT_PLANS
from ai_reusable_generation import normalize_parameters, _validate_requested_output
import ai_reusable_generation as reusable


def test_free_plus_pro_generation_contract_is_locked():
    expected = {
        "free": (10, 10, 20, 30, 100),
        "plus": (40, 120, 100, 150, 300),
        "pro": (100, 350, 210, 350, 600),
    }
    for plan, values in expected.items():
        p = STUDENT_PLANS[plan]
        assert (p["summary_monthly_pages"], p["podcast_monthly_minutes"],
                p["quiz_monthly_questions"], p["mind_map_monthly_nodes"],
                p["flashcard_monthly_cards"]) == values


def test_document_generation_has_no_daily_request_cap():
    assert "check_daily_limit" not in reusable.generate_document_material.__code__.co_names


def test_backend_accepts_only_supported_generation_parameters():
    assert normalize_parameters("podcast", {"duration_minutes": 10}) == {"duration_minutes": 10}
    try:
        normalize_parameters("podcast", {"duration_minutes": 10, "arbitrary_credits": 999})
        assert False
    except ValueError:
        pass


def test_exact_output_cardinality_is_required():
    assert _validate_requested_output(
        "summary", {"sections": [{}, {}]}, {"max_pages": 2}
    )["sections"]
    try:
        _validate_requested_output("summary", {"sections": [{}]}, {"max_pages": 2})
        assert False
    except ValueError:
        pass


def test_podcast_audio_contract_verifies_exact_duration():
    from pathlib import Path
    source = Path("podcast_audio.py").read_text()
    assert "duration_verified" in source
    assert "abs(duration_seconds - target_duration_seconds) <= 0.05" in source
    assert "requested_duration_seconds" in source


def test_ada_token_contract():
    assert ADA_TOKEN_LIMITS == {
        "free": {"daily": 20_000, "monthly": 500_000, "output": 800},
        "plus": {"daily": 100_000, "monthly": 2_500_000, "output": 1_200},
        "pro": {"daily": 250_000, "monthly": 6_000_000, "output": 1_600},
    }


def test_podcast_duration_is_part_of_artifact_identity():
    from ai_artifact_fingerprint import build_generation_fingerprint
    ten = build_generation_fingerprint(
        content_hash="doc", material_type="podcast",
        parameters={"duration_minutes": 10},
    )
    twenty = build_generation_fingerprint(
        content_hash="doc", material_type="podcast",
        parameters={"duration_minutes": 20},
    )
    assert ten != twenty


def test_generation_refunds_reference_original_entitlement():
    source = reusable.generate_document_material.__code__
    assert "quota_entitlement_id" in source.co_varnames
    assert "refund_ai_quota" in source.co_names
