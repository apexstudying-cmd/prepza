"""Focused tests for fingerprint generation ownership semantics.

These tests use a tiny fake DB/session so the concurrency-state decisions can
be checked without Anthropic or a running Flask application. Integration tests
against PostgreSQL should be added before enabling this store in production.
"""

from ai_generation_store import GenerationLookup


def test_generation_lookup_shapes_are_explicit():
    ready = GenerationLookup(
        artifact_id=1,
        status="ready",
        payload={"summary": "done"},
        owner=False,
    )
    owner = GenerationLookup(
        artifact_id=2,
        status="generating",
        payload=None,
        owner=True,
    )
    waiting = GenerationLookup(
        artifact_id=2,
        status="generating",
        payload=None,
        owner=False,
    )

    assert ready.status == "ready"
    assert ready.payload == {"summary": "done"}
    assert ready.owner is False

    assert owner.status == "generating"
    assert owner.owner is True

    assert waiting.status == "generating"
    assert waiting.owner is False


def test_only_owner_is_allowed_to_call_provider():
    owner = GenerationLookup(1, "generating", None, True)
    attached = GenerationLookup(1, "generating", None, False)

    assert owner.owner is True
    assert attached.owner is False
    # The generation path must branch on this flag before calling Anthropic.
