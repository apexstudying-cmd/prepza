"""No-network contract tests for Prepza's external provider boundaries.

These tests deliberately replace all HTTP/AWS clients. They verify request shape,
signature handling, and idempotent caller contracts; they do not claim live
provider credentials, sandbox checkout, email delivery, or GPU availability.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import importlib

import pytest

import ai_service
import object_storage


class FakeResponse:
    def __init__(self, payload=None, content=b"", status_code=200):
        self._payload = payload or {}
        self.content = content
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"fake HTTP status {self.status_code}")

    def json(self):
        return self._payload


def test_openai_generation_uses_configured_model_and_token_ceiling_without_network(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "ci-only-openai-key")
    calls = []

    def fake_post(url, *, headers, json, timeout):
        calls.append({"url": url, "headers": headers, "payload": json, "timeout": timeout})
        return FakeResponse({
            "output_text": "A mocked answer for a controlled provider test.",
            "usage": {"input_tokens": 17, "output_tokens": 9},
        })

    monkeypatch.setattr(ai_service.requests, "post", fake_post)
    text, usage = ai_service.MultiProvider._openai(
        "openai:gpt-5-mini", "Answer academically.", "Define photosynthesis.", 120
    )

    assert text == "A mocked answer for a controlled provider test."
    assert usage.input_tokens == 17
    assert usage.output_tokens == 9
    assert len(calls) == 1
    assert calls[0]["url"] == "https://api.openai.com/v1/responses"
    assert calls[0]["headers"]["Authorization"] == "Bearer ci-only-openai-key"
    assert calls[0]["payload"]["model"] == "gpt-5-mini"
    assert calls[0]["payload"]["max_output_tokens"] == 120


def test_openai_generation_fails_closed_without_a_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def forbidden_network_call(*args, **kwargs):
        raise AssertionError("OpenAI network boundary must not be called without a key")

    monkeypatch.setattr(ai_service.requests, "post", forbidden_network_call)
    with pytest.raises(ai_service.AIProviderError, match="OPENAI_API_KEY is not configured"):
        ai_service.MultiProvider._openai("openai:gpt-5-mini", "system", "input", 32)


def test_r2_object_write_read_head_presign_and_delete_use_logical_prefix(monkeypatch):
    class FakeS3:
        def __init__(self):
            self.objects = {}
            self.calls = []

        def put_object(self, **kwargs):
            self.calls.append(("put_object", kwargs))
            self.objects[(kwargs["Bucket"], kwargs["Key"])] = {
                "Body": kwargs["Body"], "ContentType": kwargs["ContentType"],
            }

        def get_object(self, **kwargs):
            self.calls.append(("get_object", kwargs))
            stored = self.objects[(kwargs["Bucket"], kwargs["Key"])]
            return {"Body": io.BytesIO(stored["Body"])}

        def head_object(self, **kwargs):
            self.calls.append(("head_object", kwargs))
            stored = self.objects[(kwargs["Bucket"], kwargs["Key"])]
            return {"ContentLength": len(stored["Body"]), "ContentType": stored["ContentType"]}

        def generate_presigned_url(self, operation, *, Params, ExpiresIn):
            self.calls.append(("presign", {"operation": operation, "Params": Params, "ExpiresIn": ExpiresIn}))
            return f"https://r2.test.invalid/{operation}?expires={ExpiresIn}"

        def delete_object(self, **kwargs):
            self.calls.append(("delete_object", kwargs))
            self.objects.pop((kwargs["Bucket"], kwargs["Key"]), None)

    monkeypatch.setenv("PREPZA_R2_ENDPOINT", "https://r2.test.invalid")
    monkeypatch.setenv("PREPZA_R2_ACCESS_KEY_ID", "test-access-key")
    monkeypatch.setenv("PREPZA_R2_SECRET_ACCESS_KEY", "test-secret-key")
    monkeypatch.setenv("PREPZA_R2_BUCKET", "prepza-test-bucket")
    fake = FakeS3()
    monkeypatch.setattr(object_storage, "_r2_client", lambda: fake)

    assert object_storage.r2_enabled() is True
    assert object_storage.r2_put_bytes("podcast-audio", "/campaigns/qa.mp3", b"audio-bytes", "audio/mpeg")
    key = ("prepza-test-bucket", "podcast-audio/campaigns/qa.mp3")
    assert fake.objects[key]["Body"] == b"audio-bytes"
    assert object_storage.r2_get_bytes("podcast-audio", "campaigns/qa.mp3") == b"audio-bytes"
    assert object_storage.r2_head("podcast-audio", "campaigns/qa.mp3")["ContentLength"] == 11
    signed = object_storage.r2_presigned_get("podcast-audio", "campaigns/qa.mp3", expires_in=999999)
    assert "expires=604800" in signed
    assert object_storage.r2_delete("podcast-audio", "campaigns/qa.mp3") is True
    assert key not in fake.objects
    assert [name for name, _ in fake.calls].count("put_object") == 1
    assert [name for name, _ in fake.calls].count("delete_object") == 1


def test_ses_send_email_builds_a_message_but_uses_only_fake_client(monkeypatch):
    from app import app as flask_app
    import auth_otp

    monkeypatch.setenv("AWS_SES_REGION", "eu-north-1")
    monkeypatch.setenv("SES_FROM_EMAIL", "prepza-ci-sender@example.invalid")

    class FakeSES:
        def __init__(self):
            self.request = None

        def send_email(self, **kwargs):
            self.request = kwargs
            return {"MessageId": "mock-ses-message-id"}

    fake = FakeSES()
    monkeypatch.setattr(auth_otp.boto3, "client", lambda service, region_name: fake)
    send_email = flask_app.extensions["prepza_auth_otp"]["send_email"]
    result = send_email(
        "student@example.invalid", "Prepza verification test",
        "Plain test body", "<p>HTML test body</p>", "verification",
    )

    assert result == "mock-ses-message-id"
    assert fake.request["FromEmailAddress"] == "prepza-ci-sender@example.invalid"
    assert fake.request["Destination"]["ToAddresses"] == ["student@example.invalid"]
    assert fake.request["Content"]["Simple"]["Body"]["Text"]["Data"] == "Plain test body"
    assert fake.request["Content"]["Simple"]["Body"]["Html"]["Data"] == "<p>HTML test body</p>"


def test_paystack_b2b_webhook_rejects_invalid_signature_and_accepts_signed_ignored_event(monkeypatch):
    from app import app as flask_app

    secret = "ci-only-paystack-webhook-secret"
    monkeypatch.setenv("PAYSTACK_SECRET_KEY", secret)
    client = flask_app.test_client()
    raw_body = b'{"event":"charge.failed","data":{"reference":"PZA-CI-NO-CHARGE"}}'

    rejected = client.post(
        "/payment/paystack/b2b-webhook", data=raw_body,
        content_type="application/json",
        headers={"x-paystack-signature": "invalid"},
    )
    assert rejected.status_code == 401

    signature = hmac.new(secret.encode(), raw_body, hashlib.sha512).hexdigest()
    accepted = client.post(
        "/payment/paystack/b2b-webhook", data=raw_body,
        content_type="application/json",
        headers={"x-paystack-signature": signature},
    )
    assert accepted.status_code == 200
    assert accepted.get_json().get("ignored") is True


def test_kokoro_worker_synthesis_request_can_be_verified_without_gpu_or_audio_provider(monkeypatch):
    monkeypatch.setenv("PREPZA_INTERNAL_BASE_URL", "http://127.0.0.1:5000")
    monkeypatch.setenv("PREPZA_INTERNAL_TOKEN", "ci-only-worker-token")
    monkeypatch.setenv("R2_ENDPOINT_URL", "https://r2.test.invalid")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "ci-only-r2-key")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "ci-only-r2-secret")
    monkeypatch.setenv("KOKORO_LOCAL_URL", "http://127.0.0.1:8880")

    import kokoro_worker.worker as worker
    worker = importlib.reload(worker)
    calls = []

    def fake_post(url, *, json, timeout):
        calls.append({"url": url, "payload": json, "timeout": timeout})
        return FakeResponse(content=b"mock-wav-bytes")

    monkeypatch.setattr(worker.requests, "post", fake_post)
    result = worker._synthesize_turn("Explain standard deviation.", "bm_george")

    assert result == b"mock-wav-bytes"
    assert calls == [{
        "url": "http://127.0.0.1:8880/v1/audio/speech",
        "payload": {
            "model": worker.KOKORO_MODEL,
            "voice": "bm_george",
            "input": "Explain standard deviation.",
            "response_format": "wav",
        },
        "timeout": worker.KOKORO_TIMEOUT_SECONDS,
    }]
