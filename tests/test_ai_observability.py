"""Privacy-safe observability contracts for Morio's AI routing boundary."""
import json
import logging

import pytest

import ai_service


class FakeProvider:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)

    def call(self, **kwargs):
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    @staticmethod
    def provider_name(model):
        return "openai"


def test_success_returns_trace_id_and_logs_metrics_without_prompt_or_answer(monkeypatch, caplog):
    secret_prompt = "PRIVATE_PROMPT_SENTINEL"
    secret_answer = "PRIVATE_ANSWER_SENTINEL"
    provider = FakeProvider([
        (secret_answer, ai_service.AIUsage(input_tokens=11, output_tokens=7, cache_read_tokens=3))
    ])
    monkeypatch.setattr(ai_service, "_get_provider", lambda: (provider, "multi"))
    caplog.set_level(logging.INFO, logger=ai_service.__name__)

    response = ai_service.route_and_generate(ai_service.AIRequest(
        task="TUTORING",
        system_prompt=secret_prompt,
        user_message="PRIVATE_USER_MESSAGE_SENTINEL",
    ))

    assert response.trace_id
    assert len(response.trace_id) == 32
    records = [json.loads(record.message) for record in caplog.records if record.message.startswith("{")]
    completed = next(record for record in records if record["event"] == "ai_request_completed")
    assert completed["trace_id"] == response.trace_id
    assert completed["task"] == "TUTORING"
    assert completed["provider"] == "openai"
    assert completed["latency_ms"] >= 0
    assert completed["input_tokens"] == 11
    assert completed["output_tokens"] == 7
    assert completed["cache_read_tokens"] == 3
    assert secret_prompt not in caplog.text
    assert secret_answer not in caplog.text
    assert "PRIVATE_USER_MESSAGE_SENTINEL" not in caplog.text


def test_fallback_logs_failed_attempt_and_success_with_same_trace_id(monkeypatch, caplog):
    task_config = dict(ai_service.AI_TASKS["TUTORING"], fallback=ai_service.MODEL_OPENAI_GPT5_MINI)
    monkeypatch.setitem(ai_service.AI_TASKS, "TUTORING", task_config)
    provider = FakeProvider([
        RuntimeError("do not log this provider message"),
        ("safe answer", ai_service.AIUsage(input_tokens=2, output_tokens=3)),
    ])
    monkeypatch.setattr(ai_service, "_get_provider", lambda: (provider, "multi"))
    caplog.set_level(logging.WARNING, logger=ai_service.__name__)

    response = ai_service.route_and_generate(ai_service.AIRequest(
        task="TUTORING", system_prompt="system", user_message="question"
    ))

    records = [json.loads(record.message) for record in caplog.records if record.message.startswith("{")]
    failed = next(record for record in records if record["event"] == "ai_attempt_failed")
    completed = next(record for record in records if record["event"] == "ai_request_completed")
    assert response.escalated is True
    assert failed["trace_id"] == response.trace_id == completed["trace_id"]
    assert failed["exception_type"] == "RuntimeError"
    assert "do not log this provider message" not in caplog.text


def test_all_provider_failures_return_trace_id_for_support_without_logging_secrets(monkeypatch, caplog):
    provider = FakeProvider([RuntimeError("provider-secret")])
    monkeypatch.setattr(ai_service, "_get_provider", lambda: (provider, "multi"))
    caplog.set_level(logging.ERROR, logger=ai_service.__name__)

    with pytest.raises(ai_service.AIProviderError, match=r"trace_id=[0-9a-f]{32}") as exc:
        ai_service.route_and_generate(ai_service.AIRequest(
            task="TUTORING", system_prompt="private", user_message="private"
        ))

    trace_id = exc.value.args[0].split("trace_id=")[1].rstrip(")")
    records = [json.loads(record.message) for record in caplog.records if record.message.startswith("{")]
    failed = next(record for record in records if record["event"] == "ai_request_failed")
    assert failed["trace_id"] == trace_id
    assert failed["exception_type"] == "RuntimeError"
    assert "provider-secret" not in caplog.text
