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
    fake_app = types.SimpleNamespace(db=fake_db, DocumentContent=object, AiJob=_FakeAiJob)

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
        db=types.SimpleNamespace(session=session), DocumentContent=object, AiJob=_FakeAiJob
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
