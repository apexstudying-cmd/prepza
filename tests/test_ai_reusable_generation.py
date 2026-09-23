import sys
import types
from dataclasses import dataclass, field
from decimal import Decimal

import pytest

from ai_generation_store import GenerationLookup
from ai_reusable_generation import normalize_parameters
import ai_reusable_generation as reusable


# These tests intentionally stay provider-free: normalization is part of the artifact identity contract.
def test_normalize_parameters_is_deterministic_and_whitespace_safe():
    assert normalize_parameters(
        "podcast",
        {"language": "  English   ", "duration_minutes": 15, "style": " conversational  "},
    ) == {
        "duration_minutes": 15,
        "language": "English",
        "style": "conversational",
    }


def test_normalize_parameters_rejects_unknown_keys():
    with pytest.raises(ValueError, match="Unsupported podcast parameter"):
        normalize_parameters("podcast", {"duration_minutes": 15, "student_id": 42})


def test_normalize_parameters_rejects_invalid_counts():
    for value in (0, -1, True, "10"):
        with pytest.raises(ValueError):
            normalize_parameters("quiz", {"question_count": value})


def test_normalize_parameters_rejects_blank_strings():
    with pytest.raises(ValueError):
        normalize_parameters("summary", {"language": "   "})


def test_normalize_parameters_rejects_unknown_material_type():
    with pytest.raises(ValueError):
        normalize_parameters("essay", {})


def test_empty_parameters_are_canonical():
    assert normalize_parameters("mind_map", None) == {}
    assert normalize_parameters("mind_map", {}) == {}


@dataclass
class _FakeUsage:
    input_tokens: int = 10
    output_tokens: int = 20
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    cost_usd: Decimal = Decimal("0")


@dataclass
class _FakeResponse:
    text: str = '{"title":"Reusable"}'
    model_used: str = "fake-model"
    provider: str = "fake-provider"
    usage: _FakeUsage = field(default_factory=_FakeUsage)


class _FakeSession:
    def __init__(self, content):
        self.content = content
        self.commits = 0
        self.rollbacks = 0
        self.added = []

    def get(self, model, object_id):
        return self.content if object_id == 7 or object_id == 8 else None

    def add(self, value):
        self.added.append(value)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class _FakeAiJob:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def test_first_generation_calls_provider_and_second_identical_request_reuses(monkeypatch):
    content = types.SimpleNamespace(content_hash="hash-7", extracted_text="course notes", page_count=3)
    session = _FakeSession(content)
    fake_db = types.SimpleNamespace(session=session)
    fake_app = types.SimpleNamespace(db=fake_db, DocumentContent=object, AiJob=_FakeAiJob, Document=object)

    class FakeProviderError(Exception):
        pass

    class FakeBudgetError(Exception):
        pass

    class FakeRateError(Exception):
        pass

    route_calls = []
    usage_calls = []
    limit_calls = []
    material_calls = []
    claim_results = [
        GenerationLookup(11, "generating", None, True),
        GenerationLookup(11, "ready", {"title": "Reusable"}, False),
    ]

    fake_ai = types.SimpleNamespace(
        AIRequest=lambda **kwargs: kwargs,
        AI_TASKS={"SUMMARIZATION": {"max_tokens": 1536}},
        AIBudgetExceededError=FakeBudgetError,
        AIRateLimitExceededError=FakeRateError,
        AIProviderError=FakeProviderError,
        is_spend_cap_reached=lambda: False,
        check_daily_limit=lambda *args, **kwargs: (limit_calls.append(args) or (True, 0, 5)),
        route_and_generate=lambda request: (route_calls.append(request) or _FakeResponse()),
        log_usage=lambda *args, **kwargs: usage_calls.append((args, kwargs)),
    )

    monkeypatch.setitem(sys.modules, "app", fake_app)
    monkeypatch.setitem(sys.modules, "ai_service", fake_ai)
    monkeypatch.setattr(reusable, "_content_scope", lambda *_: ("shared", None))
    monkeypatch.setattr(
        reusable,
        "_generator",
        lambda material_type: ("system", lambda raw: {"title": "Reusable"}, "SUMMARIZATION"),
    )
    monkeypatch.setattr(reusable, "claim_or_get_generation", lambda **kwargs: claim_results.pop(0))
    monkeypatch.setattr(reusable, "mark_generation_ready", lambda *args: None)
    monkeypatch.setattr(reusable, "_material_from_payload", lambda **kwargs: material_calls.append(kwargs) or types.SimpleNamespace(id=99))

    first = reusable.generate_document_material(
        material_type="summary",
        document_content_id=7,
        triggering_user_id=101,
        parameters={"language": " English "},
    )
    second = reusable.generate_document_material(
        material_type="summary",
        document_content_id=7,
        triggering_user_id=101,
        parameters={"language": "English"},
    )

    assert first["reused"] is False
    assert second["reused"] is True
    assert first["payload"] == second["payload"]
    assert len(route_calls) == 1
    assert len(usage_calls) == 1
    assert len(limit_calls) == 1
    assert len(material_calls) == 2


def test_reused_ready_artifact_does_not_check_entitlement(monkeypatch):
    content = types.SimpleNamespace(content_hash="hash-8", extracted_text="notes", page_count=1)
    session = _FakeSession(content)
    fake_app = types.SimpleNamespace(
        db=types.SimpleNamespace(session=session), DocumentContent=object, Document=object, AiJob=_FakeAiJob
    )

    class FakeProviderError(Exception):
        pass

    limit_called = []
    fake_ai = types.SimpleNamespace(
        AIRequest=lambda **kwargs: kwargs,
        AI_TASKS={},
        AIBudgetExceededError=Exception,
        AIRateLimitExceededError=Exception,
        AIProviderError=FakeProviderError,
        is_spend_cap_reached=lambda: (_ for _ in ()).throw(AssertionError("spend cap checked on reuse")),
        check_daily_limit=lambda *args, **kwargs: limit_called.append(True),
        route_and_generate=lambda request: (_ for _ in ()).throw(AssertionError("provider called on reuse")),
    )

    monkeypatch.setitem(sys.modules, "app", fake_app)
    monkeypatch.setitem(sys.modules, "ai_service", fake_ai)
    monkeypatch.setattr(reusable, "_content_scope", lambda *_: ("shared", None))
    monkeypatch.setattr(
        reusable,
        "claim_or_get_generation",
        lambda **kwargs: GenerationLookup(22, "ready", {"title": "Existing"}, False),
    )
    monkeypatch.setattr(reusable, "_material_from_payload", lambda **kwargs: types.SimpleNamespace(id=100))

    result = reusable.generate_document_material(
        material_type="summary",
        document_content_id=8,
        triggering_user_id=202,
        parameters={},
    )

    assert result["reused"] is True
    assert result["material_id"] == 100
    assert limit_called == []


def test_flashcard_variant_pool_rotates_four_versions_before_reuse(monkeypatch):
    content = types.SimpleNamespace(content_hash="hash-flash", extracted_text="course notes", page_count=4)
    session = _FakeSession(content)
    fake_app = types.SimpleNamespace(
        db=types.SimpleNamespace(session=session), DocumentContent=object, Document=object, AiJob=_FakeAiJob
    )

    class FakeProviderError(Exception):
        pass
    class FakeBudgetError(Exception):
        pass
    class FakeRateError(Exception):
        pass

    seen_variants = []
    provider_calls = []
    variant_state = {"next": 1}
    claim_count = {"value": 0}

    fake_usage = types.SimpleNamespace(
        FEATURES={"flashcards": ("flashcard_generations", "flashcard_max_cards")},
        check_and_consume_ai_quota=lambda *args, **kwargs: (True, {"period_start": "2026-09-01"}),
        mark_generation_variant_ready=lambda *args, **kwargs: None,
        reserve_generation_variant=lambda *args, **kwargs: (
            seen_variants.append(variant_state["next"]) or
            variant_state.update(next=1 if variant_state["next"] == 4 else variant_state["next"] + 1) or
            seen_variants[-1]
        ),
        refund_ai_quota=lambda *args, **kwargs: None,
    )

    fake_ai = types.SimpleNamespace(
        AIRequest=lambda **kwargs: kwargs,
        AI_TASKS={"FLASHCARDS": {"max_tokens": 1536}},
        AIBudgetExceededError=FakeBudgetError,
        AIRateLimitExceededError=FakeRateError,
        AIProviderError=FakeProviderError,
        is_spend_cap_reached=lambda: False,
        check_daily_limit=lambda *args, **kwargs: (True, 0, 20),
        route_and_generate=lambda request: (provider_calls.append(request) or _FakeResponse(
            text='{"cards":[{"q":"Q","a":"A"}]}'
        )),
        log_usage=lambda *args, **kwargs: None,
        FLASHCARDS_JSON_SYSTEM_PROMPT="system",
        _parse_flashcards_json=lambda raw: {"cards": [{"q": "Q", "a": "A"}]},
    )

    monkeypatch.setitem(sys.modules, "app", fake_app)
    monkeypatch.setitem(sys.modules, "ai_service", fake_ai)
    monkeypatch.setitem(sys.modules, "usage_billing", fake_usage)
    monkeypatch.setattr(reusable, "_content_scope", lambda *_: ("shared", None))
    monkeypatch.setattr(reusable, "_generator", lambda *args, **kwargs: ("system", lambda raw: {"cards": [{"q": "Q", "a": "A"}]}, "FLASHCARDS"))
    monkeypatch.setattr(
        reusable,
        "build_generation_fingerprint",
        lambda **kwargs: f"base-{kwargs['parameters'].get('variant', 'none')}",
    )
    def fake_claim(**kwargs):
        claim_count["value"] += 1
        if claim_count["value"] == 5:
            return GenerationLookup(44, "ready", {"cards": [{"q": "Q4", "a": "A4"}]}, False)
        return GenerationLookup(40 + claim_count["value"], "generating", None, True, f"lease-{claim_count['value']}")
    monkeypatch.setattr(reusable, "claim_or_get_generation", fake_claim)
    monkeypatch.setattr(reusable, "mark_generation_ready", lambda *args: None)
    monkeypatch.setattr(reusable, "_material_from_payload", lambda **kwargs: types.SimpleNamespace(id=kwargs.get("material_id", 1)))

    for _ in range(5):
        reusable.generate_document_material(
            material_type="flashcards",
            document_content_id=7,
            triggering_user_id=101,
            parameters={"card_count": 20, "difficulty": "balanced", "language": "en"},
        )

    assert seen_variants == [1, 2, 3, 4, 1]
    assert len(provider_calls) == 4


def test_all_document_materials_use_the_shared_four_variant_pool():
    import inspect

    assert set(reusable.PROMPT_VERSIONS) == {
        "summary", "quiz", "flashcards", "podcast", "mind_map"
    }
    source = inspect.getsource(reusable.generate_document_material)
    assert "variant_pool_feature = material_type in PROMPT_VERSIONS" in source
    assert "reserve_generation_variant" in source
    assert "mark_generation_variant_ready" in source
    assert "release_generation_variant" in source
