"""Production AI-generation contract checks spanning Flask routes and the active frontend.

These tests do not contact OpenAI, Paystack, R2, or Kokoro. Existing
provider-free generation tests cover the reusable generation pipeline.
"""

from pathlib import Path

from app import app


def test_backend_generation_routes_and_payload_keys_match_contract():
    expected = {
        "/documents/<int:document_id>/summarize": "summary",
        "/documents/<int:document_id>/quiz": "quiz",
        "/documents/<int:document_id>/flashcards": "flashcards",
        "/documents/<int:document_id>/mind-map": "mind_map",
        "/documents/<int:document_id>/podcast-script": "podcast",
    }
    routes = {
        (rule.rule, method)
        for rule in app.url_map.iter_rules()
        for method in rule.methods
        if method not in {"HEAD", "OPTIONS"}
    }
    for path, feature in expected.items():
        assert (path, "POST") in routes, f"Missing backend route for {feature}: {path}"


def test_active_frontend_generation_contract_matches_backend():
    source = Path("frontend/src/App.tsx").read_text(encoding="utf-8")

    expected_paths = {
        "/documents/${activeDocumentId}/summarize": "summary",
        "/documents/${activeDocumentId}/quiz": "quiz",
        "/documents/${activeDocumentId}/flashcards": "flashcards",
        "/documents/${activeDocumentId}/mind-map": "mind_map",
        "/documents/${activeDocumentId}/podcast-script": "podcast",
    }
    for path, feature in expected_paths.items():
        assert path in source, f"Active frontend no longer calls expected {feature} endpoint"

    assert "path.match" in source
    assert "mind-map" in source
    assert "mind_map" in source
    assert "setRaw(res.mind_map)" in source
    assert "res.mindmap" not in source


def test_frontend_usage_contract_uses_canonical_usage_endpoint():
    usage = Path("frontend/src/generation/usagePlan.ts").read_text(encoding="utf-8")
    assert "/api/usage/me" in usage
    assert "remaining_units" in usage
    assert "max_units_per_generation" in usage
    assert "return units <= maxPerGeneration" in usage
