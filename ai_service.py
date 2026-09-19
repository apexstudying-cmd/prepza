"""
ai_service.py — Prepza's AI pipeline (Chunk 3).

This module is the ONLY place in the codebase that should ever call an
AI provider's SDK directly. Every feature (forum "Ask Prepza AI", and
later the AI Tutor / Summaries / Quizzes / Flashcards / Podcasts / Mind
maps) is expected to call the functions in this module rather than
touching `anthropic` (or any future provider SDK) itself. That is what
makes it possible to add/swap providers later without rewriting every
feature that uses AI - see PREPZA AI COST OPTIMIZATION & MULTI-MODEL
ROUTING doc.

Deferred imports: functions below do `from app import db, ...` INSIDE
the function body rather than at module level. app.py imports this
module, so a top-level `from app import ...` here would be a circular
import. Deferring it means Python only resolves it once app.py has
already finished building the Flask app / db / models, which is always
true by the time a request handler actually calls into ai_service.

Nothing in this file talks to Flask `request`/`session` directly - it
takes plain arguments and returns plain data/dicts, so it can be unit
tested without a request context.
"""

import os
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

import anthropic
import requests


# ============================================================
# 1. PROVIDER-AGNOSTIC REQUEST / RESPONSE / USAGE SHAPES
# ============================================================
# Per the cost-optimization doc: features build an AIRequest and get
# back an AIResponse. Nothing here is Anthropic-specific by name, even
# though AnthropicProvider is currently the only implementation.

@dataclass
class AIRequest:
    task: str                      # one of AI_TASKS keys, e.g. "FORUM_ANSWER"
    system_prompt: str
    user_message: str
    max_tokens: int = 1024
    cacheable_system: bool = False  # True => system prompt sent with cache_control
    image_b64: Optional[str] = None       # base64-encoded image, for vision tasks (e.g. OCR)
    image_media_type: Optional[str] = None  # e.g. "image/png"


@dataclass
class AIUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    cost_usd: Decimal = Decimal("0")


@dataclass
class AIResponse:
    text: str
    model_used: str
    provider: str
    usage: AIUsage
    latency_ms: int
    escalated: bool = False        # True if the fallback model had to be used
    escalation_reason: Optional[str] = None


class AIProviderError(Exception):
    """Raised when every model in a task's routing chain fails."""


class AIBudgetExceededError(Exception):
    """Raised when the global monthly spend cap has been hit."""


class AIRateLimitExceededError(Exception):
    """Raised when a user has hit their daily fresh-generation limit."""


# ============================================================
# 2. TASK-BASED MODEL ROUTING
# ============================================================
# Central config so nothing downstream hard-codes a model name.
# Only Sonnet 5 / Haiku 4.5 exist today (single provider: Anthropic).
# Adding a second provider later means adding entries here, not
# touching call sites. Routing choices below follow the locked
# decisions (Sonnet for real academic reasoning, Haiku for cheap/
# mechanical generation) - tune with real usage data later per the
# cost doc's "model evaluation harness" (not built yet, deliberately
# out of scope for this pass).

MODEL_SONNET_5 = "claude-sonnet-5"
MODEL_HAIKU_4_5 = "claude-haiku-4-5-20251001"

MODEL_GEMINI_FLASH_LITE = "gemini:gemini-2.5-flash-lite"
MODEL_GEMINI_FLASH = "gemini:gemini-2.5-flash"
MODEL_OPENAI_LUNA = "openai:gpt-5.6-luna"

def _configured_model(task_name, default):
    """Allow provider/model swaps through environment without code changes."""
    return os.environ.get(f"PREPZA_AI_MODEL_{task_name.upper()}", default)

AI_TASKS = {
    # Wired and in use this chunk:
    "FORUM_ANSWER": {
        "primary": MODEL_SONNET_5,
        "fallback": None,
        "max_tokens": 1024,
        "notes": "Ask Prepza AI in the forum - real academic reasoning needed.",
    },
    "THREAD_SUMMARY": {
        "primary": MODEL_HAIKU_4_5,
        "fallback": MODEL_SONNET_5,
        "max_tokens": 512,
        "notes": "Summarizing an existing forum thread on request.",
    },

    "OCR_TRANSCRIBE": {
        "primary": MODEL_HAIKU_4_5,
        "fallback": MODEL_SONNET_5,
        "max_tokens": 2048,
        "notes": "Vision transcription of a scanned/image-only document page.",
    },

    # Reserved for the next pass of Chunk 3 (document text extraction
    # must land first) - present now so routes/features can be added
    # later without another routing-config change.
    "TUTORING": {
        "primary": MODEL_SONNET_5,
        "fallback": None,
        "max_tokens": 1024,
        "notes": "AI Tutor chat, grounded in a student's document once extraction exists.",
    },
    "SUMMARIZATION": {
        "primary": _configured_model("summarization", MODEL_HAIKU_4_5),
        "fallback": MODEL_SONNET_5,
        "max_tokens": 1536,
        "notes": "Condensed notes from a document; provider can be switched after quality benchmarking.",
    },
    "FLASHCARDS": {
        "primary": _configured_model("flashcards", MODEL_HAIKU_4_5),
        "fallback": MODEL_SONNET_5,
        "max_tokens": 2048,
        "notes": "Structured Q/A generation; provider can be switched after quality benchmarking.",
    },
    "QUIZZES": {
        "primary": _configured_model("quizzes", MODEL_SONNET_5),
        "fallback": MODEL_SONNET_5,
        "max_tokens": 2048,
        "notes": "Needs correct distractors/answers; use a cheaper model only after quality validation.",
    },
    "DOCUMENT_ANALYSIS": {
        "primary": MODEL_SONNET_5,
        "fallback": None,
        "max_tokens": 2048,
        "notes": "Classifying/understanding an uploaded document as a whole.",
    },
    "PODCAST_SCRIPT": {
        "primary": MODEL_SONNET_5,
        "fallback": None,
        "max_tokens": 3072,
        "notes": "Longer-form generation, benefits from a stronger model.",
    },
    "MIND_MAP": {
        "primary": _configured_model("mind_map", MODEL_HAIKU_4_5),
        "fallback": MODEL_SONNET_5,
        "max_tokens": 1536,
        "notes": "Structural generation; provider can be switched after quality benchmarking.",
    },
}


# ============================================================
# 3. PRICING (per MTok, USD) - keyed by effective date since Anthropic
#    has an announced Sonnet 5 price change on 2026-08-31.
#    Re-verify against platform.claude.com/docs if this drifts far
#    from today's date. Cache multipliers apply to the INPUT price only.
# ============================================================

_PRICING_SCHEDULE = {
    MODEL_GEMINI_FLASH_LITE: [(datetime(2000, 1, 1), Decimal("0.10"), Decimal("0.40"))],
    MODEL_GEMINI_FLASH: [(datetime(2000, 1, 1), Decimal("0.30"), Decimal("2.50"))],
    MODEL_OPENAI_LUNA: [(datetime(2000, 1, 1), Decimal("0.20"), Decimal("1.20"))],
    MODEL_SONNET_5: [
        # Anthropic's current official price is $2/$10 per MTok. The
        # previously announced Sep-2026 increase to $3/$15 was cancelled.
        (datetime(2000, 1, 1), Decimal("2.00"), Decimal("10.00")),
    ],
    MODEL_HAIKU_4_5: [
        (datetime(2000, 1, 1), Decimal("1.00"), Decimal("5.00")),
    ],
}

CACHE_READ_MULTIPLIER = Decimal("0.1")
CACHE_WRITE_5MIN_MULTIPLIER = Decimal("1.25")
CACHE_WRITE_1HOUR_MULTIPLIER = Decimal("2.0")


def _pricing_for(model, at=None):
    at = at or datetime.utcnow()
    schedule = _PRICING_SCHEDULE.get(model)
    if not schedule:
        raise ValueError(f"No pricing configured for model '{model}'")
    applicable = [row for row in schedule if row[0] <= at]
    return applicable[-1] if applicable else schedule[0]


# Message Batches API pricing (flat 50% off standard rates, per
# Anthropic's docs). Not date-scheduled like _PRICING_SCHEDULE above,
# since both models' batch rates have only ever been this one price -
# re-verify against platform.claude.com/docs if that changes.
_BATCH_PRICING = {
    MODEL_SONNET_5: (Decimal("1.00"), Decimal("5.00")),
    MODEL_HAIKU_4_5: (Decimal("0.50"), Decimal("2.50")),
}


def compute_cost_usd(model, input_tokens, output_tokens,
                      cache_read_tokens=0, cache_creation_tokens=0,
                      cache_ttl="5m", at=None, batch=False):
    """
    Computes cost in USD from real token counts (never estimates).
    `input_tokens` here should be the NON-cached portion only - callers
    pass the API response's input_tokens field, which Anthropic already
    reports net of cache reads/writes. Pass batch=True for requests that
    went through route_and_generate_batch (Message Batches API pricing).
    """
    if batch:
        pricing = _BATCH_PRICING.get(model)
        if not pricing:
            raise ValueError(f"No batch pricing configured for model '{model}'")
        input_rate, output_rate = pricing
    else:
        _, input_rate, output_rate = _pricing_for(model, at=at)

    cost = Decimal(input_tokens) * input_rate / Decimal(1_000_000)
    cost += Decimal(output_tokens) * output_rate / Decimal(1_000_000)

    if cache_read_tokens:
        cost += Decimal(cache_read_tokens) * input_rate * CACHE_READ_MULTIPLIER / Decimal(1_000_000)

    if cache_creation_tokens:
        write_multiplier = CACHE_WRITE_1HOUR_MULTIPLIER if cache_ttl == "1h" else CACHE_WRITE_5MIN_MULTIPLIER
        cost += Decimal(cache_creation_tokens) * input_rate * write_multiplier / Decimal(1_000_000)

    return cost.quantize(Decimal("0.000001"))


# ============================================================
# 4. PROVIDER (Anthropic) + ROUTER (primary -> fallback escalation)
# ============================================================

class AnthropicProvider:
    """Thin wrapper around the Anthropic SDK. Not imported/used outside this file."""

    def __init__(self, api_key):
        if not api_key:
            raise AIProviderError("ANTHROPIC_API_KEY is not configured")
        self._client = anthropic.Anthropic(api_key=api_key)

    def call(self, model, system_prompt, user_message, max_tokens, cacheable_system=False,
              image_b64=None, image_media_type=None):
        if cacheable_system:
            system = [{
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }]
        else:
            system = system_prompt

        if image_b64:
            user_content = [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": image_media_type, "data": image_b64},
                },
                {"type": "text", "text": user_message},
            ]
        else:
            user_content = user_message

        response = self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_content}],
        )

        text = "".join(block.text for block in response.content if block.type == "text")
        usage = response.usage

        return text, AIUsage(
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
        )



class MultiProvider:
    """Provider adapter for Anthropic, Gemini REST, and OpenAI REST.

    Keys are read only from the server environment. They must never be
    committed to the repository or sent through chat.
    """

    def __init__(self):
        self._anthropic = AnthropicProvider(os.environ.get("ANTHROPIC_API_KEY")) if os.environ.get("ANTHROPIC_API_KEY") else None

    @staticmethod
    def _gemini(model, system_prompt, user_message, max_tokens):
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise AIProviderError("GEMINI_API_KEY is not configured")
        model_id = model.split(":", 1)[1]
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent",
            headers={"x-goog-api-key": key, "Content-Type": "application/json"},
            json={
                "system_instruction": {"parts": [{"text": system_prompt}]},
                "contents": [{"parts": [{"text": user_message}]}],
                "generationConfig": {"maxOutputTokens": max_tokens},
            },
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        parts = ((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
        if not text:
            raise AIProviderError("Gemini returned no text")
        meta = data.get("usageMetadata") or {}
        return text, AIUsage(
            input_tokens=int(meta.get("promptTokenCount", 0) or 0),
            output_tokens=int(meta.get("candidatesTokenCount", 0) or 0),
        )

    @staticmethod
    def _openai(model, system_prompt, user_message, max_tokens):
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise AIProviderError("OPENAI_API_KEY is not configured")
        model_id = model.split(":", 1)[1]
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model_id,
                "instructions": system_prompt,
                "input": user_message,
                "max_output_tokens": max_tokens,
            },
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        text = data.get("output_text") or ""
        if not text:
            # Defensive fallback for response shapes that expose content blocks.
            chunks = []
            for item in data.get("output", []) or []:
                for block in item.get("content", []) or []:
                    if isinstance(block, dict) and block.get("type") in ("output_text", "text"):
                        chunks.append(block.get("text", ""))
            text = "".join(chunks)
        if not text:
            raise AIProviderError("OpenAI returned no text")
        usage = data.get("usage") or {}
        return text, AIUsage(
            input_tokens=int(usage.get("input_tokens", 0) or 0),
            output_tokens=int(usage.get("output_tokens", 0) or 0),
        )

    def call(self, model, system_prompt, user_message, max_tokens, cacheable_system=False,
             image_b64=None, image_media_type=None):
        if model.startswith("gemini:"):
            if image_b64:
                raise AIProviderError("Gemini adapter currently supports text-only generation")
            return self._gemini(model, system_prompt, user_message, max_tokens)
        if model.startswith("openai:"):
            if image_b64:
                raise AIProviderError("OpenAI adapter currently supports text-only generation")
            return self._openai(model, system_prompt, user_message, max_tokens)
        if not self._anthropic:
            raise AIProviderError("ANTHROPIC_API_KEY is not configured")
        return self._anthropic.call(
            model, system_prompt, user_message, max_tokens,
            cacheable_system=cacheable_system,
            image_b64=image_b64, image_media_type=image_media_type,
        )

    @staticmethod
    def provider_name(model):
        if model.startswith("gemini:"):
            return "google"
        if model.startswith("openai:"):
            return "openai"
        return "anthropic"


def _get_provider():
    return MultiProvider(), "multi"


def route_and_generate(ai_request: AIRequest) -> AIResponse:
    """
    Resolves an AIRequest to a task's primary model, calls it, and
    escalates to the task's fallback model on failure. This is a
    failure-triggered escalation only (the provider errored/timed
    out) - quality-gated escalation (validating the primary model's
    answer and escalating on low confidence) is a documented future
    upgrade, not built here; the AIResponse.escalated/escalation_reason
    fields exist so that logic can slot in later without another
    schema change.
    """
    task_config = AI_TASKS.get(ai_request.task)
    if not task_config:
        raise ValueError(f"Unknown AI task '{ai_request.task}'")

    provider, provider_name = _get_provider()
    max_tokens = ai_request.max_tokens or task_config["max_tokens"]

    models_to_try = [task_config["primary"]]
    if task_config.get("fallback"):
        models_to_try.append(task_config["fallback"])

    last_error = None
    for attempt, model in enumerate(models_to_try):
        start = time.monotonic()
        try:
            text, usage = provider.call(
                model=model,
                system_prompt=ai_request.system_prompt,
                user_message=ai_request.user_message,
                max_tokens=max_tokens,
                cacheable_system=ai_request.cacheable_system,
                image_b64=ai_request.image_b64,
                image_media_type=ai_request.image_media_type,
            )
            latency_ms = int((time.monotonic() - start) * 1000)
            usage.cost_usd = compute_cost_usd(
                model, usage.input_tokens, usage.output_tokens,
                usage.cache_read_tokens, usage.cache_creation_tokens,
            )
            actual_provider = provider.provider_name(model) if hasattr(provider, "provider_name") else provider_name
            return AIResponse(
                text=text,
                model_used=model,
                provider=actual_provider,
                usage=usage,
                latency_ms=latency_ms,
                escalated=(attempt > 0),
                escalation_reason="primary_model_failed" if attempt > 0 else None,
            )
        except Exception as e:  # noqa: BLE001 - genuinely want to catch+retry any provider failure
            last_error = e
            continue

    raise AIProviderError(f"All models failed for task '{ai_request.task}': {last_error}")


# ============================================================
# 4b. MESSAGE BATCHES API (50% cheaper, async) - for background/non-
#     real-time work only. Never call this from a request handler; it
#     blocks the calling thread while polling, so it must only ever be
#     called from a background thread (e.g. document_pipeline.py's
#     extraction thread) so a slow batch never holds up a user request.
# ============================================================

# How often to poll an in-progress batch, and the longest this call
# will wait before giving up and raising. Batches "often finish in
# minutes" per Anthropic's docs even though the SLA is 24h, so this
# cap is deliberately much shorter than the SLA - a batch still running
# past this point is treated as unusually slow, not waited out further.
# The batch itself keeps processing on Anthropic's side regardless;
# callers that give up here can check back later via the batch_id.
BATCH_POLL_INTERVAL_SECONDS = 15
BATCH_MAX_WAIT_SECONDS = 20 * 60


def _build_message_params(model, ai_request, max_tokens):
    """
    Builds the request-shape dict for one Messages API call, used by
    the batch path below. (Mirrors AnthropicProvider.call's shape -
    kept as a separate small function rather than refactoring .call()
    itself, to avoid touching the already-working synchronous path.)
    """
    if ai_request.cacheable_system:
        system = [{
            "type": "text",
            "text": ai_request.system_prompt,
            "cache_control": {"type": "ephemeral"},
        }]
    else:
        system = ai_request.system_prompt

    if ai_request.image_b64:
        user_content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": ai_request.image_media_type,
                    "data": ai_request.image_b64,
                },
            },
            {"type": "text", "text": ai_request.user_message},
        ]
    else:
        user_content = ai_request.user_message

    return {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user_content}],
    }


def route_and_generate_batch(task, items, on_batch_created=None):
    """
    Submits multiple AIRequests for the same task as a single Anthropic
    Message Batch (50% cheaper than synchronous calls - see
    _BATCH_PRICING). `items` is a list of (custom_id, AIRequest) tuples.

    `on_batch_created`, if given, is called with the batch's id right
    after submission (before polling starts) - callers can use this to
    persist the id somewhere (e.g. AiJob.batch_id) so it's inspectable
    even if this call is interrupted before finishing.

    Returns (batch_id, results) where results is a dict of
    {custom_id: AIResponse} for succeeded items and
    {custom_id: AIProviderError} for anything errored/expired/canceled -
    callers decide whether to retry those synchronously.

    Unlike route_and_generate, there is no primary/fallback escalation
    here - all items in a batch use the task's primary model. A failed
    item should be retried (synchronously, or in a future batch), not
    silently escalated.
    """
    task_config = AI_TASKS.get(task)
    if not task_config:
        raise ValueError(f"Unknown AI task '{task}'")

    provider, provider_name = _get_provider()
    model = task_config["primary"]
    max_tokens = task_config["max_tokens"]

    batch_requests = [
        {"custom_id": custom_id, "params": _build_message_params(model, ai_request, max_tokens)}
        for custom_id, ai_request in items
    ]

    batch = provider._client.messages.batches.create(requests=batch_requests)
    batch_id = batch.id

    if on_batch_created:
        on_batch_created(batch_id)

    elapsed = 0
    while True:
        batch = provider._client.messages.batches.retrieve(batch_id)
        if batch.processing_status == "ended":
            break
        time.sleep(BATCH_POLL_INTERVAL_SECONDS)
        elapsed += BATCH_POLL_INTERVAL_SECONDS
        if elapsed >= BATCH_MAX_WAIT_SECONDS:
            raise AIProviderError(
                f"Batch {batch_id} for task '{task}' did not finish within "
                f"{BATCH_MAX_WAIT_SECONDS}s (status: {batch.processing_status}). "
                f"It will keep processing on Anthropic's side - check the "
                f"Anthropic Console with this batch id if needed."
            )

    results = {}
    for result in provider._client.messages.batches.results(batch_id):
        custom_id = result.custom_id
        if result.result.type == "succeeded":
            message = result.result.message
            text = "".join(block.text for block in message.content if block.type == "text")
            usage = message.usage
            ai_usage = AIUsage(
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
                cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
            )
            ai_usage.cost_usd = compute_cost_usd(
                model, ai_usage.input_tokens, ai_usage.output_tokens,
                ai_usage.cache_read_tokens, ai_usage.cache_creation_tokens,
                batch=True,
            )
            results[custom_id] = AIResponse(
                text=text, model_used=model, provider=provider_name,
                usage=ai_usage, latency_ms=0,
            )
        else:
            results[custom_id] = AIProviderError(
                f"Batch item '{custom_id}' ended as '{result.result.type}'"
            )

    return batch_id, results


# ============================================================
# 5. USAGE LOGGING
# ============================================================

def log_usage(user_id, request_type, model=None, provider=None,
               usage: Optional[AIUsage] = None, forum_reply_id=None):
    """
    Logs one row to ai_usage_log. `request_type` describes what kind of
    request this was - 'answer' | 'reuse' | 'summarize' | 'quiz' (more
    values are added as generation features grow; the column has no
    DB-level constraint, this list is documentation only). For 'reuse'
    rows, model/provider stay None and usage stays zeroed - no API call
    was made.
    """
    from app import db, AiUsageLog

    usage = usage or AIUsage()
    entry = AiUsageLog(
        user_id=user_id,
        forum_reply_id=forum_reply_id,
        request_type=request_type,
        model=model,
        provider=provider,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_read_tokens=usage.cache_read_tokens,
        cache_creation_tokens=usage.cache_creation_tokens,
        cost_usd=usage.cost_usd,
    )
    db.session.add(entry)
    db.session.commit()
    return entry


# ============================================================
# 6. RATE LIMITS (per-user daily fresh generations)
# ============================================================

DAILY_FRESH_GENERATION_LIMITS = {
    "free": 5,
    "plus": 15,
    "premium": None,  # None = unlimited
}

_DAILY_LIMIT_SETTING_KEYS = {
    "free": "ai_daily_limit_free",
    "plus": "ai_daily_limit_plus",
    "premium": "ai_daily_limit_premium",
}


def get_daily_limit_for_tier(plan_tier):
    """
    Reads the daily fresh-generation cap for a plan tier from
    SystemSetting (admin-editable via /admin/settings), falling back
    to the hardcoded DAILY_FRESH_GENERATION_LIMITS default if unset or
    unparseable. A stored value of "unlimited" (case-insensitive) means
    no cap, matching the existing None-means-unlimited convention.
    """
    from app import SystemSetting

    default = DAILY_FRESH_GENERATION_LIMITS.get(plan_tier, DAILY_FRESH_GENERATION_LIMITS["free"])
    setting_key = _DAILY_LIMIT_SETTING_KEYS.get(plan_tier)
    if not setting_key:
        return default

    setting = SystemSetting.query.filter_by(key=setting_key).first()
    if not setting or setting.value is None or setting.value == "":
        return default

    if setting.value.strip().lower() == "unlimited":
        return None

    try:
        return int(setting.value)
    except ValueError:
        return default


def get_daily_fresh_generation_count(user_id):
    """
    Counts this user's FRESH (non-reuse) generations in the last 24h,
    computed from ai_usage_log rather than a counter column on User -
    avoids reset/drift bugs, per the locked decision.
    """
    from app import db, AiUsageLog

    cutoff = datetime.utcnow() - timedelta(hours=24)
    return (
        db.session.query(AiUsageLog)
        .filter(
            AiUsageLog.user_id == user_id,
            AiUsageLog.request_type != "reuse",
            AiUsageLog.created_at >= cutoff,
        )
        .count()
    )


def check_daily_limit(user_id, plan_tier="free"):
    """
    Returns (allowed: bool, used: int, limit: int | None).
    `plan_tier` defaults to "free" for everyone today since User.plan
    doesn't exist yet - callers can pass a real tier once it does,
    without this function needing to change.
    """
    limit = get_daily_limit_for_tier(plan_tier)
    if limit is None:
        return True, 0, None

    used = get_daily_fresh_generation_count(user_id)
    return used < limit, used, limit


# ============================================================
# 6b. RATE LIMITS (per-user daily TUTOR messages) - separate pool
# ============================================================
# Deliberately NOT shared with DAILY_FRESH_GENERATION_LIMITS above - a
# single tutoring session is many back-and-forth messages, and sharing
# the document-generation pool would let one conversation exhaust a
# free student's entire day. Same SystemSetting-backed override
# pattern as get_daily_limit_for_tier(), just keyed on
# ai_daily_tutor_limit_* instead of ai_daily_limit_*.

DAILY_FRESH_TUTOR_LIMITS = {
    "free": 5,
    "plus": 20,
    "premium": 50,
    # premium is a soft abuse-guard here, not a real cost ceiling - see
    # the ai_monthly_budget_usd global circuit breaker below for that.
}

_DAILY_TUTOR_LIMIT_SETTING_KEYS = {
    "free": "ai_daily_tutor_limit_free",
    "plus": "ai_daily_tutor_limit_plus",
    "premium": "ai_daily_tutor_limit_premium",
}


def get_daily_tutor_limit_for_tier(plan_tier):
    """
    Reads the daily tutor-message cap for a plan tier from
    SystemSetting (admin-editable via /admin/settings), falling back
    to DAILY_FRESH_TUTOR_LIMITS if unset or unparseable. Mirrors
    get_daily_limit_for_tier() exactly, just against the tutor-specific
    keys/defaults.
    """
    from app import SystemSetting

    default = DAILY_FRESH_TUTOR_LIMITS.get(plan_tier, DAILY_FRESH_TUTOR_LIMITS["free"])
    setting_key = _DAILY_TUTOR_LIMIT_SETTING_KEYS.get(plan_tier)
    if not setting_key:
        return default

    setting = SystemSetting.query.filter_by(key=setting_key).first()
    if not setting or setting.value is None or setting.value == "":
        return default

    if setting.value.strip().lower() == "unlimited":
        return None

    try:
        return int(setting.value)
    except ValueError:
        return default


def get_daily_fresh_tutor_count(user_id):
    """
    Counts this user's tutor messages in the last 24h. Filters on
    request_type == "tutor_message" specifically (not != "reuse" like
    get_daily_fresh_generation_count()) since tutor messages are their
    own separate pool entirely, not a "fresh vs reused" distinction.
    """
    from app import db, AiUsageLog

    cutoff = datetime.utcnow() - timedelta(hours=24)
    return (
        db.session.query(AiUsageLog)
        .filter(
            AiUsageLog.user_id == user_id,
            AiUsageLog.request_type == "tutor_message",
            AiUsageLog.created_at >= cutoff,
        )
        .count()
    )


def check_daily_tutor_limit(user_id, plan_tier="free"):
    """
    Returns (allowed: bool, used: int, limit: int | None). Same shape
    as check_daily_limit() above, against the tutor-specific pool.
    """
    limit = get_daily_tutor_limit_for_tier(plan_tier)
    if limit is None:
        return True, 0, None

    used = get_daily_fresh_tutor_count(user_id)
    return used < limit, used, limit


# ============================================================
# 7. GLOBAL SPEND CIRCUIT BREAKER (monthly)
# ============================================================

DEFAULT_MONTHLY_AI_BUDGET_USD = Decimal("300.00")
_AI_BUDGET_SETTING_KEY = "ai_monthly_budget_usd"


def get_monthly_ai_budget_usd():
    """
    Reads the configurable monthly cap from SystemSetting (same table/
    pattern as price_notes etc.), defaulting to $20 if unset.
    """
    from app import db, SystemSetting

    setting = SystemSetting.query.filter_by(key=_AI_BUDGET_SETTING_KEY).first()
    if not setting or not setting.value:
        return DEFAULT_MONTHLY_AI_BUDGET_USD
    try:
        return Decimal(setting.value)
    except Exception:
        return DEFAULT_MONTHLY_AI_BUDGET_USD


def get_monthly_ai_spend_usd():
    from app import db, AiUsageLog

    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total = (
        db.session.query(db.func.coalesce(db.func.sum(AiUsageLog.cost_usd), 0))
        .filter(AiUsageLog.created_at >= month_start)
        .scalar()
    )
    return Decimal(total or 0)


def is_spend_cap_reached():
    """
    True => fresh generation should pause app-wide. Cached/reused
    answers (cost $0, request_type='reuse') must keep working - callers
    should only call this before a FRESH generation, never before
    serving a reuse-cache hit.
    """
    return get_monthly_ai_spend_usd() >= get_monthly_ai_budget_usd()


# ============================================================
# 8. REUSE CACHE (Postgres full-text + trigram, no embeddings)
# ============================================================

# Below this similarity score, a cached answer isn't considered a
# reliable enough match to reuse - falls through to a fresh generation.
REUSE_SIMILARITY_THRESHOLD = 0.35


def find_reusable_answer(question_text, unit_id=None):
    """
    Searches ai_answer for a sufficiently similar existing question
    using tsvector full-text ranking combined with pg_trgm similarity
    (search_vector and the trigram index are already built into the
    ai_answer table). Returns the best-matching AiAnswer row, or None.

    Deliberately unit-scoped when unit_id is given: a good answer about
    ACT 101 supply/demand shouldn't get served for a MAT 101 question
    that happens to share vocabulary.
    """
    from app import db, AiAnswer
    from sqlalchemy import text as sql_text

    query = sql_text("""
        SELECT id, similarity(question_text, :q) AS sim
        FROM ai_answer
        WHERE (:unit_id IS NULL OR unit_id = :unit_id)
          AND (
                search_vector @@ plainto_tsquery('english', :q)
                OR question_text % :q
              )
        ORDER BY sim DESC
        LIMIT 1
    """)

    row = db.session.execute(query, {"q": question_text, "unit_id": unit_id}).first()
    if not row or row.sim is None or row.sim < REUSE_SIMILARITY_THRESHOLD:
        return None

    return db.session.get(AiAnswer, row.id)


# ============================================================
# 9. HIGH-LEVEL ORCHESTRATION - forum "Ask Prepza AI"
# ============================================================
# This is the one function the forum routes (next stage) should call.
# Everything above is plumbing; this is the feature.

def answer_forum_question(question_text, unit, triggering_user_id, plan_tier="free"):
    """
    Full pipeline for one "Ask Prepza AI" / @Prepza AI invocation:
      1. Reuse-cache check (always tried first, zero cost, no limits apply)
      2. Spend-cap check (only blocks FRESH generation)
      3. Daily rate-limit check (only blocks FRESH generation)
      4. Generate via the router, log usage, cache the new answer

    `unit` is a Unit model instance (or None for a general question).
    Returns a dict: {answer_text, ai_answer_id, reused, model_used}.
    Raises AIBudgetExceededError / AIRateLimitExceededError when a
    fresh generation is blocked - callers should catch these and
    return a clear message to the student rather than a generic 500.
    """
    from app import db, AiAnswer

    unit_id = unit.id if unit else None

    cached = find_reusable_answer(question_text, unit_id=unit_id)
    if cached:
        cached.reuse_count = (cached.reuse_count or 0) + 1
        db.session.commit()
        log_usage(triggering_user_id, request_type="reuse")
        return {
            "answer_text": cached.answer_text,
            "ai_answer_id": cached.id,
            "reused": True,
            "model_used": cached.model_used,
        }

    if is_spend_cap_reached():
        raise AIBudgetExceededError(
            "Prepza AI has reached its monthly budget - fresh answers are paused, "
            "but existing answers are still available."
        )

    allowed, used, limit = check_daily_limit(triggering_user_id, plan_tier=plan_tier)
    if not allowed:
        raise AIRateLimitExceededError(
            f"You've used {used}/{limit} AI questions today - try again tomorrow, "
            "or search for an existing answer."
        )

    unit_context = f"{unit.code} - {unit.name}" if unit else "a general academic topic"
    system_prompt = (
        "You are Prepza AI, an academic assistant for university students on the Prepza "
        "study platform. Answer clearly and correctly for a student studying "
        f"{unit_context}. If you are not confident in an answer, say so rather than "
        "guessing. Keep answers focused and study-friendly - use structure (steps, "
        "short sections) for anything multi-part."
    )

    ai_response = route_and_generate(AIRequest(
        task="FORUM_ANSWER",
        system_prompt=system_prompt,
        user_message=question_text,
        cacheable_system=True,
    ))

    log_usage(
        triggering_user_id,
        request_type="answer",
        model=ai_response.model_used,
        provider=ai_response.provider,
        usage=ai_response.usage,
    )

    new_answer = AiAnswer(
        unit_id=unit_id,
        question_text=question_text,
        answer_text=ai_response.text,
        model_used=ai_response.model_used,
        input_tokens=ai_response.usage.input_tokens,
        output_tokens=ai_response.usage.output_tokens,
        cache_read_tokens=ai_response.usage.cache_read_tokens,
        cache_creation_tokens=ai_response.usage.cache_creation_tokens,
        cost_usd=ai_response.usage.cost_usd,
        reuse_count=0,
    )
    db.session.add(new_answer)
    db.session.commit()

    return {
        "answer_text": ai_response.text,
        "ai_answer_id": new_answer.id,
        "reused": False,
        "model_used": ai_response.model_used,
    }



# ============================================================
# 10. CONTINUATION-RETRY CALL (summarization only)
# ============================================================
# route_and_generate()/AnthropicProvider.call() intentionally discard
# stop_reason - fine for forum answers, which rarely truncate. Summaries
# are longer and JSON-structured, so a max_tokens cutoff mid-JSON is a
# real failure mode. This function is a separate, low-level path used
# ONLY by generate_document_summary() below - it does not touch
# route_and_generate() or any other feature's call path.
#
# Continuation approach: on truncation, resend the same system prompt
# and user message, but append the partial output as a prefilled
# assistant turn (no new user turn) so the model continues writing from
# exactly where it stopped. Capped at one continuation (2 attempts
# total) per the locked decision - still-truncated after that is
# treated as a failure, not retried further.

CONTINUATION_MAX_ATTEMPTS = 2


def _call_with_continuation(task, system_prompt, user_message, max_tokens=None, cacheable_system=True):
    """
    Like route_and_generate(), but detects max_tokens truncation and
    retries with a prefilled continuation instead of returning a
    truncated response. Uses the task's primary model only - no
    primary/fallback escalation here (truncation isn't a provider
    failure, so escalating models wouldn't help). Returns an AIResponse
    whose usage/cost reflects the SUM of all attempts made.
    """
    task_config = AI_TASKS.get(task)
    if not task_config:
        raise ValueError(f"Unknown AI task '{task}'")

    provider, provider_name = _get_provider()
    model = task_config["primary"]
    resolved_max_tokens = max_tokens or task_config["max_tokens"]

    accumulated_text = ""
    total_usage = AIUsage()
    start = time.monotonic()

    if cacheable_system:
        system = [{
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"},
        }]
    else:
        system = system_prompt
    for attempt in range(CONTINUATION_MAX_ATTEMPTS):
        if accumulated_text:
            messages = [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": accumulated_text},
            ]
        else:
            messages = [{"role": "user", "content": user_message}]

        response = provider._client.messages.create(
            model=model,
            max_tokens=resolved_max_tokens,
            system=system,
            messages=messages,
        )

        chunk_text = "".join(block.text for block in response.content if block.type == "text")
        accumulated_text += chunk_text

        usage = response.usage
        total_usage.input_tokens += usage.input_tokens
        total_usage.output_tokens += usage.output_tokens
        total_usage.cache_read_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0
        total_usage.cache_creation_tokens += getattr(usage, "cache_creation_input_tokens", 0) or 0

        if response.stop_reason != "max_tokens":
            break

    latency_ms = int((time.monotonic() - start) * 1000)
    total_usage.cost_usd = compute_cost_usd(
        model, total_usage.input_tokens, total_usage.output_tokens,
        total_usage.cache_read_tokens, total_usage.cache_creation_tokens,
    )

    return AIResponse(
        text=accumulated_text,
        model_used=model,
        provider=provider_name,
        usage=total_usage,
        latency_ms=latency_ms,
    )


# ============================================================
# 11. HIGH-LEVEL ORCHESTRATION - document Summaries
# ============================================================
# Mirrors answer_forum_question()'s shape (cache check -> spend cap ->
# rate limit -> generate -> log -> persist), but the cache here is a
# simple exact-key lookup on GeneratedMaterial(document_content_id,
# material_type='summary') rather than fuzzy text matching - a
# document's summary is either already generated for that exact
# content hash, or it isn't.

SUMMARY_JSON_SYSTEM_PROMPT = (
    "You are Prepza AI, generating a condensed study summary from a student's "
    "uploaded document for the Prepza study platform. Read the provided document "
    "text and produce a summary as STRICT JSON ONLY - no markdown code fences, no "
    "preamble, no text before or after the JSON object. The JSON must have this "
    "exact shape:\n"
    '{"title": "string", "subtitle": "string (e.g. \'Generated from your N-page '
    'notes\')", "sections": [{"title": "string", "body": "string"}]}\n\n'
    "Guidelines: choose the number of sections based on how the material "
    "naturally divides (usually 3-6). Each section body should be dense, "
    "exam-focused, plain text - use \\n\\n for paragraph breaks within a body. "
    "Write mathematical notation in plain unicode (e.g. A(t) = A(0)(1+i)^t, "
    "using ^ for exponents is acceptable, or unicode superscripts if natural) - "
    "never LaTeX. Do not invent content not present in the source text."
)


def _parse_summary_json(raw_text):
    """
    Parses the model's summary JSON, tolerating stray markdown code
    fences some models add despite instructions not to. Raises
    ValueError on anything that doesn't match the expected shape -
    caller treats this as a failed generation, not a crash.
    """
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    data = json.loads(cleaned)

    if not isinstance(data, dict):
        raise ValueError("Summary JSON root must be an object")
    if "title" not in data or "sections" not in data:
        raise ValueError("Summary JSON missing required \'title\' or \'sections\' key")
    if not isinstance(data["sections"], list) or not data["sections"]:
        raise ValueError("Summary JSON \'sections\' must be a non-empty list")
    for section in data["sections"]:
        if not isinstance(section, dict) or "title" not in section or "body" not in section:
            raise ValueError("Each summary section must have \'title\' and \'body\'")

    return data


def generate_document_summary(document_content_id, triggering_user_id, plan_tier="free", parameters=None):
    from ai_reusable_generation import generate_document_material
    return generate_document_material(
        material_type="summary",
        document_content_id=document_content_id,
        triggering_user_id=triggering_user_id,
        plan_tier=plan_tier,
        parameters=parameters,
    )

def _legacy_generate_document_summary(document_content_id, triggering_user_id, plan_tier="free"):
    """
    Full pipeline for generating (or reusing) a document's AI summary:
      1. Cache check - an existing ready GeneratedMaterial(material_type=
         'summary') for this document_content_id is reused for free, no
         limits apply.
      2. Requires DocumentContent.extracted_text to be populated -
         callers should not invoke this before text extraction has
         completed.
      3. Spend-cap check (only blocks FRESH generation)
      4. Daily rate-limit check (only blocks FRESH generation)
      5. Generate via _call_with_continuation, parse JSON, log usage,
         persist to GeneratedMaterial.

    Returns a dict: {payload: dict, material_id, reused, model_used}.
    Raises AIBudgetExceededError / AIRateLimitExceededError /
    AIProviderError - callers should catch these the same way the
    forum routes do.

    Known simplification (v1): no locking against a second concurrent
    trigger for the same document while one generation is already in
    flight - matches the "not handled yet" posture already taken
    elsewhere in this codebase (e.g. concurrent forum posts).
    """
    from app import db, DocumentContent, GeneratedMaterial

    content = db.session.get(DocumentContent, document_content_id)
    if not content:
        raise ValueError(f"DocumentContent {document_content_id} not found")

    existing = GeneratedMaterial.query.filter_by(
        document_content_id=document_content_id, material_type="summary"
    ).first()

    if existing and existing.status == "ready" and existing.payload:
        log_usage(triggering_user_id, request_type="reuse")
        return {
            "payload": json.loads(existing.payload),
            "material_id": existing.id,
            "reused": True,
            "model_used": None,
        }

    if not content.extracted_text:
        raise AIProviderError(
            "This document's text hasn't finished processing yet - try again shortly."
        )

    if is_spend_cap_reached():
        raise AIBudgetExceededError(
            "Prepza AI has reached its monthly budget - fresh summaries are paused, "
            "but existing summaries are still available."
        )

    allowed, used, limit = check_daily_limit(triggering_user_id, plan_tier=plan_tier)
    if not allowed:
        raise AIRateLimitExceededError(
            f"You've used {used}/{limit} AI questions today - try again tomorrow."
        )

    material = existing or GeneratedMaterial(
        document_content_id=document_content_id, material_type="summary"
    )
    material.status = "generating"
    material.error_message = None
    if not existing:
        db.session.add(material)
    db.session.commit()

    user_message = (
        f"Document text ({content.page_count or '?'} pages):\n\n{content.extracted_text}"
    )

    try:
        ai_response = _call_with_continuation(
            task="SUMMARIZATION",
            system_prompt=SUMMARY_JSON_SYSTEM_PROMPT,
            user_message=user_message,
        )
        parsed = _parse_summary_json(ai_response.text)
    except Exception as e:
        material.status = "failed"
        material.error_message = str(e)[:500]
        db.session.commit()
        if isinstance(e, (AIBudgetExceededError, AIRateLimitExceededError, AIProviderError)):
            raise
        raise AIProviderError(f"Summary generation failed: {e}")

    log_usage(
        triggering_user_id,
        request_type="summarize",
        model=ai_response.model_used,
        provider=ai_response.provider,
        usage=ai_response.usage,
    )

    material.payload = json.dumps(parsed)
    material.status = "ready"
    db.session.commit()

    return {
        "payload": parsed,
        "material_id": material.id,
        "reused": False,
        "model_used": ai_response.model_used,
    }


# ============================================================
# 12. HIGH-LEVEL ORCHESTRATION - document Quizzes
# ============================================================
# Same shape as generate_document_summary() (cache check -> spend cap ->
# rate limit -> generate -> log -> persist), keyed on
# GeneratedMaterial(material_type='quiz'). Uses the QUIZZES task
# (Sonnet 5, no fallback - "needs correct distractors/answers, not just
# plausible-looking ones" per AI_TASKS' own note) and the same
# continuation-retry path as summaries, since a quiz truncated mid-JSON
# is just as broken as a truncated summary.

QUIZ_JSON_SYSTEM_PROMPT = (
    "You are Prepza AI, generating a multiple-choice practice quiz from a "
    "student\'s uploaded document for the Prepza study platform. Read the "
    "provided document text and produce a quiz as STRICT JSON ONLY - no "
    "markdown code fences, no preamble, no text before or after the JSON "
    "object. The JSON must have this exact shape:\n"
    '{"title": "string", "subtitle": "string", "questions": '
    '[{"q": "string", "opts": ["string","string","string","string"], "ans": 0}]}\n\n'
    "Guidelines: produce 10-15 questions covering the material\'s key concepts, "
    "not trivial recall. Each question must have EXACTLY 4 options in \"opts\". "
    "\"ans\" is the 0-indexed position of the correct option within \"opts\" "
    "(0, 1, 2, or 3). Distractors (wrong options) must be plausible - based on "
    "common mistakes or related-but-incorrect values/concepts, not obviously "
    "wrong. Do not invent facts not supported by the source text. Write "
    "mathematical notation in plain unicode, never LaTeX."
)


def _parse_quiz_json(raw_text):
    """
    Parses the model's quiz JSON, tolerating stray markdown code fences.
    Raises ValueError on anything that doesn't match the expected shape -
    caller treats this as a failed generation, not a crash.
    """
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    data = json.loads(cleaned)

    if not isinstance(data, dict):
        raise ValueError("Quiz JSON root must be an object")
    if "title" not in data or "questions" not in data:
        raise ValueError("Quiz JSON missing required \'title\' or \'questions\' key")
    if not isinstance(data["questions"], list) or not data["questions"]:
        raise ValueError("Quiz JSON \'questions\' must be a non-empty list")
    for question in data["questions"]:
        if not isinstance(question, dict) or "q" not in question or "opts" not in question or "ans" not in question:
            raise ValueError("Each quiz question must have \'q\', \'opts\', and \'ans\'")
        if not isinstance(question["opts"], list) or len(question["opts"]) != 4:
            raise ValueError("Each quiz question\'s \'opts\' must be a list of exactly 4 options")
        if not isinstance(question["ans"], int) or isinstance(question["ans"], bool) or not (0 <= question["ans"] <= 3):
            raise ValueError("Each quiz question\'s \'ans\' must be an integer 0-3")

    return data


def generate_document_quiz(document_content_id, triggering_user_id, plan_tier="free", parameters=None):
    from ai_reusable_generation import generate_document_material
    return generate_document_material(
        material_type="quiz",
        document_content_id=document_content_id,
        triggering_user_id=triggering_user_id,
        plan_tier=plan_tier,
        parameters=parameters,
    )

def _legacy_generate_document_quiz(document_content_id, triggering_user_id, plan_tier="free"):
    """
    Full pipeline for generating (or reusing) a document's AI practice
    quiz. Identical shape to generate_document_summary() - see that
    function's docstring for the caching/limits/error semantics, which
    are the same here.

    Returns a dict: {payload: dict, material_id, reused, model_used}.
    Raises AIBudgetExceededError / AIRateLimitExceededError /
    AIProviderError - callers should catch these the same way the
    forum routes / summarize route do.
    """
    from app import db, DocumentContent, GeneratedMaterial

    content = db.session.get(DocumentContent, document_content_id)
    if not content:
        raise ValueError(f"DocumentContent {document_content_id} not found")

    existing = GeneratedMaterial.query.filter_by(
        document_content_id=document_content_id, material_type="quiz"
    ).first()

    if existing and existing.status == "ready" and existing.payload:
        log_usage(triggering_user_id, request_type="reuse")
        return {
            "payload": json.loads(existing.payload),
            "material_id": existing.id,
            "reused": True,
            "model_used": None,
        }

    if not content.extracted_text:
        raise AIProviderError(
            "This document's text hasn't finished processing yet - try again shortly."
        )

    if is_spend_cap_reached():
        raise AIBudgetExceededError(
            "Prepza AI has reached its monthly budget - fresh quizzes are paused, "
            "but existing quizzes are still available."
        )

    allowed, used, limit = check_daily_limit(triggering_user_id, plan_tier=plan_tier)
    if not allowed:
        raise AIRateLimitExceededError(
            f"You've used {used}/{limit} AI questions today - try again tomorrow."
        )

    material = existing or GeneratedMaterial(
        document_content_id=document_content_id, material_type="quiz"
    )
    material.status = "generating"
    material.error_message = None
    if not existing:
        db.session.add(material)
    db.session.commit()

    user_message = (
        f"Document text ({content.page_count or '?'} pages):\n\n{content.extracted_text}"
    )

    try:
        ai_response = _call_with_continuation(
            task="QUIZZES",
            system_prompt=QUIZ_JSON_SYSTEM_PROMPT,
            user_message=user_message,
        )
        parsed = _parse_quiz_json(ai_response.text)
    except Exception as e:
        material.status = "failed"
        material.error_message = str(e)[:500]
        db.session.commit()
        if isinstance(e, (AIBudgetExceededError, AIRateLimitExceededError, AIProviderError)):
            raise
        raise AIProviderError(f"Quiz generation failed: {e}")

    log_usage(
        triggering_user_id,
        request_type="quiz",
        model=ai_response.model_used,
        provider=ai_response.provider,
        usage=ai_response.usage,
    )

    material.payload = json.dumps(parsed)
    material.status = "ready"
    db.session.commit()

    return {
        "payload": parsed,
        "material_id": material.id,
        "reused": False,
        "model_used": ai_response.model_used,
    }




# ============================================================
# 13. HIGH-LEVEL ORCHESTRATION - document Flashcards
# ============================================================
# Same shape as generate_document_quiz() (cache check -> spend cap ->
# rate limit -> generate -> log -> persist), keyed on
# GeneratedMaterial(material_type='flashcards'). Uses the FLASHCARDS
# task (Haiku primary, Sonnet fallback - "mechanical extraction of Q/A
# pairs from source text" per AI_TASKS' own note) and the same
# continuation-retry path as summaries/quizzes.
#
# Payload shape wraps the card list in {title, subtitle, cards} for
# consistency with Summary/Quiz, even though the current flashcard
# mock screen doesn't render a title today - keeps the three
# generation features' payload shapes uniform rather than one-off.

FLASHCARDS_JSON_SYSTEM_PROMPT = (
    "You are Prepza AI, generating a set of study flashcards from a student's "
    "uploaded document for the Prepza study platform. Read the provided "
    "document text and produce flashcards as STRICT JSON ONLY - no markdown "
    "code fences, no preamble, no text before or after the JSON object. The "
    "JSON must have this exact shape:\n"
    '{"title": "string", "subtitle": "string", "cards": '
    '[{"q": "string", "a": "string"}]}\n\n'
    "Guidelines: produce 15-30 cards covering key definitions, formulas, and "
    "concepts from the material - one clear idea per card, not compound "
    "questions. \"q\" should be a short prompt (a definition, formula name, "
    "or question). \"a\" should be concise but complete - use \\n\\n to "
    "separate the core answer from a worked example or extra context where "
    "helpful, the way a physical flashcard's back would be laid out. Write "
    "mathematical notation in plain unicode (e.g. A(t) = A(0)(1+i)^t), never "
    "LaTeX. Do not invent facts not supported by the source text."
)


def _parse_flashcards_json(raw_text):
    """
    Parses the model's flashcards JSON, tolerating stray markdown code
    fences. Raises ValueError on anything that doesn't match the
    expected shape - caller treats this as a failed generation, not a
    crash.
    """
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    data = json.loads(cleaned)

    if not isinstance(data, dict):
        raise ValueError("Flashcards JSON root must be an object")
    if "title" not in data or "cards" not in data:
        raise ValueError("Flashcards JSON missing required \'title\' or \'cards\' key")
    if not isinstance(data["cards"], list) or not data["cards"]:
        raise ValueError("Flashcards JSON \'cards\' must be a non-empty list")
    for card in data["cards"]:
        if not isinstance(card, dict) or "q" not in card or "a" not in card:
            raise ValueError("Each flashcard must have \'q\' and \'a\'")
        if not isinstance(card["q"], str) or not isinstance(card["a"], str):
            raise ValueError("Each flashcard\'s \'q\' and \'a\' must be strings")

    return data


def generate_document_flashcards(document_content_id, triggering_user_id, plan_tier="free", parameters=None):
    from ai_reusable_generation import generate_document_material
    return generate_document_material(
        material_type="flashcards",
        document_content_id=document_content_id,
        triggering_user_id=triggering_user_id,
        plan_tier=plan_tier,
        parameters=parameters,
    )

def _legacy_generate_document_flashcards(document_content_id, triggering_user_id, plan_tier="free"):
    """
    Full pipeline for generating (or reusing) a document's AI
    flashcard set. Identical shape to generate_document_quiz() - see
    that function's docstring for the caching/limits/error semantics,
    which are the same here.

    Returns a dict: {payload: dict, material_id, reused, model_used}.
    Raises AIBudgetExceededError / AIRateLimitExceededError /
    AIProviderError - callers should catch these the same way the
    other document-material routes do.
    """
    from app import db, DocumentContent, GeneratedMaterial

    content = db.session.get(DocumentContent, document_content_id)
    if not content:
        raise ValueError(f"DocumentContent {document_content_id} not found")

    existing = GeneratedMaterial.query.filter_by(
        document_content_id=document_content_id, material_type="flashcards"
    ).first()

    if existing and existing.status == "ready" and existing.payload:
        log_usage(triggering_user_id, request_type="reuse")
        return {
            "payload": json.loads(existing.payload),
            "material_id": existing.id,
            "reused": True,
            "model_used": None,
        }

    if not content.extracted_text:
        raise AIProviderError(
            "This document's text hasn't finished processing yet - try again shortly."
        )

    if is_spend_cap_reached():
        raise AIBudgetExceededError(
            "Prepza AI has reached its monthly budget - fresh flashcards are paused, "
            "but existing flashcard sets are still available."
        )

    allowed, used, limit = check_daily_limit(triggering_user_id, plan_tier=plan_tier)
    if not allowed:
        raise AIRateLimitExceededError(
            f"You've used {used}/{limit} AI questions today - try again tomorrow."
        )

    material = existing or GeneratedMaterial(
        document_content_id=document_content_id, material_type="flashcards"
    )
    material.status = "generating"
    material.error_message = None
    if not existing:
        db.session.add(material)
    db.session.commit()

    user_message = (
        f"Document text ({content.page_count or '?'} pages):\n\n{content.extracted_text}"
    )

    try:
        ai_response = _call_with_continuation(
            task="FLASHCARDS",
            system_prompt=FLASHCARDS_JSON_SYSTEM_PROMPT,
            user_message=user_message,
        )
        parsed = _parse_flashcards_json(ai_response.text)
    except Exception as e:
        material.status = "failed"
        material.error_message = str(e)[:500]
        db.session.commit()
        if isinstance(e, (AIBudgetExceededError, AIRateLimitExceededError, AIProviderError)):
            raise
        raise AIProviderError(f"Flashcards generation failed: {e}")

    log_usage(
        triggering_user_id,
        request_type="flashcards",
        model=ai_response.model_used,
        provider=ai_response.provider,
        usage=ai_response.usage,
    )

    material.payload = json.dumps(parsed)
    material.status = "ready"
    db.session.commit()

    return {
        "payload": parsed,
        "material_id": material.id,
        "reused": False,
        "model_used": ai_response.model_used,
    }


# ============================================================
# 14. HIGH-LEVEL ORCHESTRATION - document Podcast Scripts (Phase 1)
# ============================================================
# Phase 1 = script text only. Audio synthesis is a deliberately
# separate follow-up (TTS provider not yet chosen - see the Podcast
# scope discussion; Render free tier rules out in-process self-hosted
# TTS). The GeneratedMaterial payload already carries audio_status/
# audio_storage_path/duration_seconds so that follow-up can update
# this SAME row once a provider is wired up.
#
# Characters (fixed cast, not per-document):
#   lec     - the teacher/lecturer
#   morio   - the sharp, advanced student
#   kichwa  - the foundational student, still catching on, asks Lec
#             the basic clarifying questions
# Speaker IDs in the JSON are clean lowercase for stable voice-ID
# lookup later. Within spoken dialogue TEXT, name mentions use a
# stress-spelled form ("Morrrrio", "Kichwaaaa") baked in at generation
# time - the standard workaround for TTS engines without SSML/emphasis
# support, so this works regardless of which engine Phase 2 picks.

PODCAST_SCRIPT_JSON_SYSTEM_PROMPT = (
    "You are Prepza AI, creating a premium study podcast SCRIPT (text only, "
    "no audio) from a student's uploaded document. The script is a real "
    "teaching conversation between three fixed recurring characters. "
    "Lec is the lecturer: calm, precise, warm, excellent at explanations, "
    "corrects misconceptions and keeps the episode coherent. "
    "Morio is the advanced student: sharp, curious and exam-focused; he asks "
    "the questions a strong student would ask, challenges assumptions and "
    "pushes toward nuance, applications and derivations. "
    "Kichwa is the foundational student: sincere, relatable and still "
    "building the basics; he asks genuine clarifying questions that expose "
    "hidden assumptions and create useful teaching moments. Kichwa is never "
    "mocked or used as comic relief.\\n\\n"
    "The three must feel like consistent people, not three voices reading "
    "bullet points. Give the episode an arc: hook the listener, establish "
    "the core idea, teach progressively, introduce examples/applications, "
    "surface common misconceptions, let Morio push deeper, let Kichwa "
    "clarify the foundations, then finish with a concise exam/study recap. "
    "Use natural transitions and callbacks so the conversation feels authored. "
    "Do not pad time with repetition, greetings, filler, or empty banter. "
    "Every exchange must teach, clarify, apply, test or connect an idea. "
    "Use light, occasional banter between Lec and Morio only when it feels "
    "natural; never sacrifice academic clarity for entertainment.\\n\\n"
    "This is text-to-speech dialogue, not prose. Keep turns reasonably short "
    "and speakable. Read numbers, symbols and formulas aloud in natural words. "
    "Never invent facts beyond the source document. If the document is unclear "
    "or incomplete, make the uncertainty explicit rather than hallucinating. "
    "Whenever a character says another character's name aloud, spell Morio as "
    "\"Morrrrio\" and Kichwa as \"Kichwaaaa\" in the spoken text field. "
    "The speaker field must remain exactly lec, morio or kichwa.\\n\\n"
    "Return STRICT JSON ONLY, with exactly: "
    '{"title":"string","subtitle":"string","turns":[{"speaker":"lec|morio|kichwa","text":"string"}]}.'
)

def build_podcast_script_system_prompt(duration_minutes=None, style=None):
    duration = int(duration_minutes or 10)
    target_words = int(round(duration * 135))
    lower = max(0, target_words - int(target_words * 0.08))
    upper = target_words + int(target_words * 0.08)
    style_text = (style or "focused_revision").replace("_", " ")
    return (
        PODCAST_SCRIPT_JSON_SYSTEM_PROMPT
        + "\\n\\n<episode_constraints>\\n"
        + f"Target spoken duration: {duration} minutes. "
        + f"Target spoken word count: {target_words} words (acceptable planning range {lower}-{upper}).\\n"
        + f"Episode style: {style_text}.\\n"
        + "Treat the word target as a real production constraint. Do not stop early "
          "because the JSON is long. Cover the source material proportionally and "
          "use additional examples or deeper explanations only when supported by "
          "the source. Do not repeat the same point merely to reach the target.\\n"
        + "</episode_constraints>"
    )

PODCAST_VALID_SPEAKERS = {"lec", "morio", "kichwa"}


def _parse_podcast_script_json(raw_text):
    """
    Parses the model's podcast script JSON, tolerating stray markdown
    code fences. Raises ValueError on anything that doesn't match the
    expected shape - caller treats this as a failed generation, not a
    crash.
    """
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    data = json.loads(cleaned)

    if not isinstance(data, dict):
        raise ValueError("Podcast script JSON root must be an object")
    if "title" not in data or "turns" not in data:
        raise ValueError("Podcast script JSON missing required \'title\' or \'turns\' key")
    if not isinstance(data["turns"], list) or not data["turns"]:
        raise ValueError("Podcast script JSON \'turns\' must be a non-empty list")
    for turn in data["turns"]:
        if not isinstance(turn, dict) or "speaker" not in turn or "text" not in turn:
            raise ValueError("Each podcast turn must have \'speaker\' and \'text\'")
        if turn["speaker"] not in PODCAST_VALID_SPEAKERS:
            raise ValueError(
                f"Podcast turn \'speaker\' must be one of {sorted(PODCAST_VALID_SPEAKERS)}, "
                f"got {turn['speaker']!r}"
            )
        if not isinstance(turn["text"], str) or not turn["text"].strip():
            raise ValueError("Each podcast turn\'s \'text\' must be a non-empty string")

    return data


def generate_document_podcast_script(document_content_id, triggering_user_id, plan_tier="free", parameters=None):
    from ai_reusable_generation import generate_document_material
    return generate_document_material(
        material_type="podcast",
        document_content_id=document_content_id,
        triggering_user_id=triggering_user_id,
        plan_tier=plan_tier,
        parameters=parameters,
    )

def _legacy_generate_document_podcast_script(document_content_id, triggering_user_id, plan_tier="free"):
    """
    Full pipeline for generating (or reusing) a document's AI podcast
    SCRIPT (Phase 1 - text only, no audio). Same caching/limits/error
    semantics as generate_document_summary()/quiz()/flashcards() - see
    those functions' docstrings.

    The persisted payload is an envelope, not just the raw script:
      {"script": {...}, "audio_status": "pending",
       "audio_storage_path": None, "duration_seconds": None}
    A later audio-synthesis pass (separate function, once a TTS
    provider is chosen) updates audio_status/audio_storage_path/
    duration_seconds on this SAME GeneratedMaterial row rather than
    creating a new one - script and audio share one row's lifecycle.

    Returns a dict: {payload: dict, material_id, reused, model_used}.
    Raises AIBudgetExceededError / AIRateLimitExceededError /
    AIProviderError - callers should catch these the same way the
    other document-material routes do.
    """
    from app import db, DocumentContent, GeneratedMaterial

    content = db.session.get(DocumentContent, document_content_id)
    if not content:
        raise ValueError(f"DocumentContent {document_content_id} not found")

    existing = GeneratedMaterial.query.filter_by(
        document_content_id=document_content_id, material_type="podcast"
    ).first()

    if existing and existing.status == "ready" and existing.payload:
        log_usage(triggering_user_id, request_type="reuse")
        return {
            "payload": json.loads(existing.payload),
            "material_id": existing.id,
            "reused": True,
            "model_used": None,
        }

    if not content.extracted_text:
        raise AIProviderError(
            "This document's text hasn't finished processing yet - try again shortly."
        )

    if is_spend_cap_reached():
        raise AIBudgetExceededError(
            "Prepza AI has reached its monthly budget - fresh podcast scripts are paused, "
            "but existing ones are still available."
        )

    allowed, used, limit = check_daily_limit(triggering_user_id, plan_tier=plan_tier)
    if not allowed:
        raise AIRateLimitExceededError(
            f"You've used {used}/{limit} AI questions today - try again tomorrow."
        )

    material = existing or GeneratedMaterial(
        document_content_id=document_content_id, material_type="podcast"
    )
    material.status = "generating"
    material.error_message = None
    if not existing:
        db.session.add(material)
    db.session.commit()

    user_message = (
        f"Document text ({content.page_count or '?'} pages):\n\n{content.extracted_text}"
    )

    try:
        ai_response = _call_with_continuation(
            task="PODCAST_SCRIPT",
            system_prompt=PODCAST_SCRIPT_JSON_SYSTEM_PROMPT,
            user_message=user_message,
        )
        parsed_script = _parse_podcast_script_json(ai_response.text)
    except Exception as e:
        material.status = "failed"
        material.error_message = str(e)[:500]
        db.session.commit()
        if isinstance(e, (AIBudgetExceededError, AIRateLimitExceededError, AIProviderError)):
            raise
        raise AIProviderError(f"Podcast script generation failed: {e}")

    log_usage(
        triggering_user_id,
        request_type="podcast_script",
        model=ai_response.model_used,
        provider=ai_response.provider,
        usage=ai_response.usage,
    )

    envelope = {
        "script": parsed_script,
        "audio_status": "pending",
        "audio_storage_path": None,
        "duration_seconds": None,
    }
    material.payload = json.dumps(envelope)
    material.status = "ready"
    db.session.commit()

    return {
        "payload": envelope,
        "material_id": material.id,
        "reused": False,
        "model_used": ai_response.model_used,
    }


# ============================================================
# HIGH-LEVEL ORCHESTRATION - Tutor Chat (Ada Phase 1)
# ============================================================
# One persistent TutorConversation per (student, document) - see the
# tutor chat design handoff. This is Phase 1 only: direct tutoring +
# best-effort concept-tagging for LearningEvent logging. No diagnostic
# teaching, no mastery scoring, no past-paper retrieval yet - those are
# later Ada phases, deliberately out of scope here.
#
# Unlike every other generate_document_*() function above, this talks
# to provider._client.messages.create() directly instead of going
# through AnthropicProvider.call() - .call() only supports a single
# user message, not a growing multi-turn history. Mirrors how
# _call_with_continuation() already bypasses .call() for its own
# reasons; same "add a parallel low-level path, don't touch the
# already-working .call() path" approach.
#
# Caching strategy: the document's extracted_text is identical on
# every turn of a given conversation, so it lives in the SYSTEM prompt
# (wrapped in cache_control, same ephemeral 5-minute pattern used
# elsewhere) - the only part of a turn's input that's expensive AND
# stable. The growing conversation history goes in the `messages` list
# instead, uncached, capped at the last TUTOR_HISTORY_MESSAGE_LIMIT
# messages so an unbounded conversation doesn't get expensive purely
# from history length (the Anthropic API is stateless - full history
# is resent every turn).
#
# Deliberately NOT using continuation-retry (_call_with_continuation)
# here - a tutor reply truncated mid-sentence by a max_tokens cutoff is
# a minor UX rough edge, not the JSON-corruption failure mode
# continuation-retry exists to solve for summaries/quizzes/flashcards.
# Revisit if this turns out to matter in practice.

TUTOR_HISTORY_MESSAGE_LIMIT = 20

# Minimum gap (in days) since the student's last message in a
# tutoring conversation before a spaced-review nudge is even
# considered - keeps this from firing mid-session, only when the
# student is genuinely returning after time away. See the Ada
# design doc's "know when to be proactive, not naggy" guidance
# (section 25).
SESSION_RETURN_GAP_DAYS = 3

# Matches a trailing "[[CONCEPT: <name>]]" marker line the tutor system
# prompt instructs the model to always end its reply with. Tolerant of
# a leading blank line and trailing whitespace; anchored to the END of
# the (already-stripped) text so it only ever matches the final line,
# never a concept mention elsewhere in the reply body.
TUTOR_CONCEPT_MARKER_RE = re.compile(r"\n?\[\[CONCEPT:\s*(.+?)\s*\]\]\s*\Z", re.IGNORECASE)

# Matches a "[[PREREQUISITE: <name>]]" marker line, same tolerant
# pattern as TUTOR_CONCEPT_MARKER_RE above. Applied as a SEPARATE pass
# after the CONCEPT marker has already been stripped (see
# _parse_tutor_reply()) - PREREQUISITE sits one line above CONCEPT, so
# it only becomes the new end-of-string once CONCEPT is gone.
TUTOR_PREREQUISITE_MARKER_RE = re.compile(r"\n?\[\[PREREQUISITE:\s*(.+?)\s*\]\]\s*\Z", re.IGNORECASE)


def _build_tutor_system_prompt(unit_context, document_text, page_count):
    """
    Builds the (cacheable) tutor system prompt: tone/behavior
    instructions, the concept-marker protocol, and the full document
    text. Kept as one string (not split into "instructions" + "doc")
    since both go into the SAME cached system-prompt block regardless.
    """
    return (
        "You are Ada, Prepza's AI tutor. You are working one-on-one with a "
        f"student on {unit_context}, grounded in the document they uploaded "
        f"({page_count or '?'} pages), reproduced in full below. Teach the "
        "way a patient, intelligent, encouraging-but-direct personal tutor "
        "would: check understanding before assuming it, explain clearly, "
        "use examples where they genuinely help, and prioritize the "
        "student actually learning the material over simply answering as "
        "fast as possible. Ground every answer in the document text below "
        "wherever it's relevant - if the student asks about something the "
        "document doesn't cover, say so rather than inventing content. "
        "Keep replies conversational and appropriately concise for a chat, "
        "not an essay.\n\n"
        "GUIDED PROBLEM-SOLVING: when the student asks you to solve, "
        "complete, or work through a specific exercise or homework-style "
        "problem, default to guided practice rather than handing over a "
        "worked solution immediately - ask what they think the first step "
        "is, evaluate their attempt, and give a hint if they're off track "
        "rather than the full answer. Escalate to a stronger hint only if "
        "a lighter one didn't help. Give the direct, complete solution "
        "when the student explicitly asks for it, says they're stuck "
        "after a genuine attempt, or still wants it spelled out after "
        "you've already offered guidance - respect a clear, direct "
        "request rather than withholding the answer out of stubbornness. "
        "This guided-practice default does NOT apply to conceptual "
        "questions (\"explain X\", \"what is Y\") - answer those "
        "directly, no hint-first detour.\n\n"
        "At the very end of EVERY reply, on its own final line, add a "
        "machine-readable marker naming the single main academic concept "
        "this turn was about, in this exact format:\n"
        "[[CONCEPT: <2-5 word concept name, Title Case>]]\n"
        "If the turn was small talk, logistics, or not about a specific "
        "academic concept, write [[CONCEPT: none]] instead. Always include "
        "exactly one such line, always last, always in this exact bracket "
        "format - it is stripped out before the student ever sees your "
        "reply, so it does not need to read naturally as part of the "
        "conversation.\n\n"
        "Directly above that CONCEPT marker line (making it the "
        "second-to-last line, not the last), add one more marker "
        "naming ONE key prerequisite concept a student would need to "
        "already understand before this turn's concept, in this exact "
        "format:\n"
        "[[PREREQUISITE: <2-5 word prerequisite concept name, Title Case>]]\n"
        "If this turn wasn't really about a specific concept, or it "
        "has no clear single prerequisite, write [[PREREQUISITE: none]] "
        "instead. This marker is also stripped out before the student "
        "sees your reply.\n\n"
        f"DOCUMENT TEXT:\n{document_text}"
    )


def _format_mastery_context(snapshot):
    """
    Turns a get_student_mastery_snapshot() result into a short
    instruction block for the tutor prompt. Returns "" for an empty
    snapshot (nothing tracked yet in this conversation) so callers can
    skip adding an empty system block.

    Explicitly instructs the model not to read the numbers back to the
    student verbatim - this is internal calibration context, not
    something Ada should narrate ("I see your mastery score is 54"
    would be exactly the kind of robotic, fabricated-sounding framing
    the Ada design doc's personality section warns against).
    """
    if not snapshot:
        return ""

    lines = [
        f"- {item['name']}: mastery {item['mastery_score']}/100 ({item['confidence']} confidence)"
        for item in snapshot
    ]
    return (
        "STUDENT MASTERY CONTEXT (from this student's history in this "
        "conversation - use it to calibrate depth and pacing, but NEVER "
        "read these numbers back to the student or mention them "
        "directly):\n" + "\n".join(lines) + "\n\n"
        "Calibration guidance: for concepts with high mastery, don't "
        "re-explain the basics - build on them or move faster. For "
        "concepts with low mastery, use more scaffolding and check "
        "understanding before advancing. 'Low' confidence means there "
        "isn't much evidence yet either way - treat that mastery number "
        "as tentative, not a reliable read on what the student actually "
        "knows."
    )


def _format_diagnostic_instruction(prerequisite_concept):
    """
    Builds a short, uncached system block instructing Ada to check the
    student's grasp of a specific prerequisite before continuing to
    teach, rather than assuming it. Kept as its own tiny system block
    (uncached, same reasoning as _format_mastery_context()) so it
    doesn't invalidate the cached document-text block on every turn.
    """
    return (
        "DIAGNOSTIC CHECK-IN: before continuing to teach, this student's "
        f"grasp of a likely prerequisite - \"{prerequisite_concept.name}\" - "
        "isn't yet well-established. Before going deeper into the current "
        "topic, ask ONE lightweight, natural question to check their "
        "understanding of this prerequisite (not a quiz, just a quick "
        "conversational check). If they show they understand it, continue "
        "teaching normally. If they don't, address the prerequisite first "
        "before returning to the original topic. Don't make this feel like "
        "an interruption or a test - it should read as a natural part of "
        "the conversation."
    )


def _format_spaced_review_instruction(due_concepts):
    """
    Builds a short, uncached system block nudging Ada to offer a
    quick refresher on previously-learned concepts the student hasn't
    practiced in a while. Only ever called when the caller has already
    confirmed both a real session gap AND non-empty due_concepts - see
    get_concepts_due_for_review() and generate_tutor_reply().
    """
    concept_list = ", ".join(f'"{c["name"]}"' for c in due_concepts)
    return (
        "WELCOME BACK: it's been a while since this student's last "
        "message in this conversation, and they haven't practiced the "
        f"following previously-learned concept(s) recently: {concept_list}. "
        "If it fits naturally, briefly offer a quick refresher or "
        "check-in on one of these before diving into new material - "
        "phrase it warmly, not as a scheduled obligation, and don't "
        "insist if the student wants to move straight on. Never mention "
        "specific mastery scores or exact day counts to the student."
    )


def _fetch_tutor_history(conversation_id, limit=TUTOR_HISTORY_MESSAGE_LIMIT):
    """
    Returns up to the last `limit` TutorMessage rows for a conversation,
    oldest first - ready to map directly into the API's `messages` list.
    """
    from app import TutorMessage

    rows = (
        TutorMessage.query.filter_by(conversation_id=conversation_id)
        .order_by(TutorMessage.created_at.desc())
        .limit(limit)
        .all()
    )
    rows.reverse()
    return rows


def _parse_tutor_reply(raw_text):
    """
    Strips the trailing [[PREREQUISITE: ...]] and [[CONCEPT: ...]]
    markers (see _build_tutor_system_prompt()) from a raw tutor reply.
    Returns (visible_reply_text, concept_name_or_None,
    prerequisite_name_or_None).

    Stripped in the order the prompt asks the model to write them:
    CONCEPT is the true last line, so it's matched and removed FIRST;
    PREREQUISITE is the line directly above it, matched against
    whatever remains. This means CONCEPT parsing behaves identically to
    before this marker existed - a missing/malformed PREREQUISITE line
    can't affect it. Both are best-effort signals for
    LearningEvent/ConceptPrerequisite logging, never something that
    blocks the reply itself from reaching the student.
    """
    stripped = raw_text.strip()

    concept_match = TUTOR_CONCEPT_MARKER_RE.search(stripped)
    if not concept_match:
        return stripped, None, None

    after_concept_strip = stripped[:concept_match.start()].strip()
    if not after_concept_strip:
        # Marker somehow ate the whole reply - never show the student
        # an empty message over a parsing edge case.
        return stripped, None, None

    concept_raw = concept_match.group(1).strip()
    concept_name = (
        None if (not concept_raw or concept_raw.lower() in ("none", "n/a"))
        else concept_raw[:200]
    )

    prerequisite_match = TUTOR_PREREQUISITE_MARKER_RE.search(after_concept_strip)
    if not prerequisite_match:
        return after_concept_strip, concept_name, None

    visible_text = after_concept_strip[:prerequisite_match.start()].strip()
    if not visible_text:
        # Same defensive fallback as above - never lose the reply body
        # over a prerequisite-marker parsing edge case.
        return after_concept_strip, concept_name, None

    prerequisite_raw = prerequisite_match.group(1).strip()
    prerequisite_name = (
        None if (not prerequisite_raw or prerequisite_raw.lower() in ("none", "n/a"))
        else prerequisite_raw[:200]
    )

    return visible_text, concept_name, prerequisite_name


def generate_tutor_reply(conversation_id, user_message_text, triggering_user_id, plan_tier="free"):
    """
    Full pipeline for one tutor-chat turn:
      1. Spend-cap check (blocks fresh generation platform-wide, same
         circuit breaker every other AI feature shares)
      2. Daily tutor-message rate-limit check - a SEPARATE pool from
         the document-generation daily cap (see check_daily_tutor_limit())
      3. Persist the student's message immediately, before the AI call
         - it must survive even if generation below fails, same
         "human content survives AI failure" posture as
         _trigger_ai_reply() in the forum feature
      4. Call Sonnet directly with a cacheable system prompt (the
         document text) + the last TUTOR_HISTORY_MESSAGE_LIMIT messages
      5. Strip the trailing concept marker, persist the assistant's
         reply, log usage, and - if a real concept was named - upsert
         LearningConcept + record a LearningEvent
      6. Bump TutorConversation.updated_at

    Returns {reply_text, concept, tutor_message_id, model_used}.
    Raises AIBudgetExceededError / AIRateLimitExceededError /
    AIProviderError - callers (the tutor routes) translate these to
    HTTP responses the same way every other AI route already does.

    Known simplification (Phase 1): no diagnostic pre-check, no
    mastery scoring, no past-paper retrieval - this is direct tutoring
    grounded in one document, plus raw learning-event logging for a
    later phase to build on. Matches the "not handled yet" honesty
    pattern used elsewhere in this codebase.
    """
    from app import (
        db, TutorConversation, TutorMessage, DocumentContent,
        LearningConcept, LearningEvent, update_concept_mastery,
        get_student_mastery_snapshot, ConceptPrerequisite,
        should_diagnose, get_current_conversation_concept_id,
        get_concepts_due_for_review,
    )

    conversation = db.session.get(TutorConversation, conversation_id)
    if not conversation:
        raise ValueError(f"TutorConversation {conversation_id} not found")

    # Captured now, before anything below bumps conversation.updated_at,
    # so the spaced-review gap check further down measures the gap
    # BEFORE this turn, not after.
    previous_activity_at = conversation.updated_at

    content = db.session.get(DocumentContent, conversation.document_content_id)
    if not content or not content.extracted_text:
        raise AIProviderError(
            "This document's text hasn't finished processing yet - try again shortly."
        )

    if is_spend_cap_reached():
        raise AIBudgetExceededError(
            "Prepza AI has reached its monthly budget - the tutor is paused for now, "
            "but your existing conversation is still here."
        )

    allowed, used, limit = check_daily_tutor_limit(triggering_user_id, plan_tier=plan_tier)
    if not allowed:
        raise AIRateLimitExceededError(
            f"You've sent {used}/{limit} tutor messages today - try again tomorrow."
        )

    # Persist the student's message now, before the AI call, so it
    # survives even if generation below fails.
    user_row = TutorMessage(conversation_id=conversation_id, role="user", content=user_message_text)
    db.session.add(user_row)
    db.session.commit()

    history_rows = _fetch_tutor_history(conversation_id)
    messages = [{"role": row.role, "content": row.content} for row in history_rows]

    task_config = AI_TASKS["TUTORING"]
    model = task_config["primary"]
    max_tokens = task_config["max_tokens"]

    system_prompt = _build_tutor_system_prompt(
        unit_context="their coursework",
        document_text=content.extracted_text,
        page_count=content.page_count,
    )

    mastery_snapshot = get_student_mastery_snapshot(triggering_user_id, content.id)
    mastery_context_text = _format_mastery_context(mastery_snapshot)

    system = [{
        "type": "text",
        "text": system_prompt,
        "cache_control": {"type": "ephemeral"},
    }]
    if mastery_context_text:
        # Deliberately a SEPARATE, uncached system block - mastery
        # scores change nearly every turn, so folding this into the
        # cached document-text block above would invalidate that
        # cache almost every request and undo Phase 1's caching cost
        # savings. This block is short, so leaving it uncached costs
        # very little.
        system.append({"type": "text", "text": mastery_context_text})

    # Ada Phase 2: diagnostic teaching. Looks at the concept most
    # recently touched in THIS conversation (not this turn's concept -
    # that's unknown until the model replies) and checks whether a
    # prerequisite gap is likely, via should_diagnose(). Fires at most
    # a short instruction block, no extra model call - reuses the same
    # single-call architecture as everything else in this function.
    current_concept_id = get_current_conversation_concept_id(triggering_user_id, content.id)
    diagnostic_prerequisite = (
        should_diagnose(triggering_user_id, current_concept_id)
        if current_concept_id else None
    )
    if diagnostic_prerequisite:
        # Same uncached-block reasoning as mastery_context_text above -
        # this can change turn to turn, so it must not ride inside the
        # cached document-text block.
        system.append({
            "type": "text",
            "text": _format_diagnostic_instruction(diagnostic_prerequisite),
        })

    # Ada: spaced-review nudge. Only surfaces when the student is
    # genuinely returning to this conversation after a real gap - not
    # on every turn within an active session.
    review_due = []
    if previous_activity_at and (datetime.utcnow() - previous_activity_at).days >= SESSION_RETURN_GAP_DAYS:
        review_due = get_concepts_due_for_review(triggering_user_id, content.id)
    if review_due:
        # Same uncached-block reasoning as the mastery/diagnostic
        # blocks above - turn-dependent, not stable document content.
        system.append({
            "type": "text",
            "text": _format_spaced_review_instruction(review_due),
        })

    provider, provider_name = _get_provider()

    start = time.monotonic()
    try:
        response = provider._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )
    except Exception as e:  # noqa: BLE001 - genuinely want to catch any provider failure
        raise AIProviderError(f"Tutor reply generation failed: {e}")
    latency_ms = int((time.monotonic() - start) * 1000)  # noqa: F841 - kept for future observability wiring

    raw_text = "".join(block.text for block in response.content if block.type == "text")
    usage = response.usage
    ai_usage = AIUsage(
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
        cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
    )
    ai_usage.cost_usd = compute_cost_usd(
        model, ai_usage.input_tokens, ai_usage.output_tokens,
        ai_usage.cache_read_tokens, ai_usage.cache_creation_tokens,
    )

    reply_text, concept_name, prerequisite_name = _parse_tutor_reply(raw_text)

    assistant_row = TutorMessage(conversation_id=conversation_id, role="assistant", content=reply_text)
    db.session.add(assistant_row)
    db.session.flush()  # assign assistant_row.id before the LearningEvent FK below references it

    log_usage(
        triggering_user_id,
        request_type="tutor_message",
        model=model,
        provider=provider_name,
        usage=ai_usage,
    )

    if concept_name:
        concept = LearningConcept.query.filter_by(name=concept_name).first()
        if not concept:
            concept = LearningConcept(name=concept_name)
            db.session.add(concept)
            db.session.flush()  # assign concept.id before the LearningEvent FK below references it
        db.session.add(LearningEvent(
            user_id=triggering_user_id,
            concept_id=concept.id,
            tutor_message_id=assistant_row.id,
            document_content_id=content.id,
            evidence_snippet=user_message_text[:500],
        ))
        # Ada Phase 2: fold this exposure into the running mastery
        # estimate for this (user, concept) pair. had_misconception is
        # always False today - nothing populates LearningEvent.misconception
        # yet, so every detected concept is treated as a plain exposure
        # signal until misconception detection is wired up.
        update_concept_mastery(triggering_user_id, concept.id, had_misconception=False)

        # Ada Phase 2: organically build the prerequisite graph, same
        # upsert pattern as LearningConcept itself. Guards against a
        # self-loop (a concept can't be its own prerequisite) since the
        # model occasionally repeats the concept name here despite the
        # prompt asking for a DIFFERENT prerequisite concept.
        if prerequisite_name and prerequisite_name != concept_name:
            prerequisite_concept = LearningConcept.query.filter_by(name=prerequisite_name).first()
            if not prerequisite_concept:
                prerequisite_concept = LearningConcept(name=prerequisite_name)
                db.session.add(prerequisite_concept)
                db.session.flush()  # assign prerequisite_concept.id before the query below
            existing_edge = ConceptPrerequisite.query.filter_by(
                concept_id=concept.id, prerequisite_concept_id=prerequisite_concept.id,
            ).first()
            if not existing_edge:
                db.session.add(ConceptPrerequisite(
                    concept_id=concept.id,
                    prerequisite_concept_id=prerequisite_concept.id,
                ))

    conversation.updated_at = datetime.utcnow()
    db.session.commit()

    return {
        "reply_text": reply_text,
        "concept": concept_name,
        "tutor_message_id": assistant_row.id,
        "model_used": model,
    }




# ============================================================
# 15. HIGH-LEVEL ORCHESTRATION - document Mind Maps
# ============================================================
# Same shape as generate_document_flashcards() (cache check -> spend cap
# -> rate limit -> generate -> log -> persist), keyed on
# GeneratedMaterial(material_type='mind_map'). Uses the MIND_MAP task
# (Haiku primary, Sonnet fallback - "structural extraction (nodes/
# edges), not deep reasoning" per AI_TASKS' own note) and the same
# continuation-retry path as the other document materials.
#
# Payload is content-only (title/subtitle/center/branches) - no x/y/
# color/layout data. Positioning a variable number of branches around
# the center node is a frontend rendering concern, not something the
# AI should be dictating pixel coordinates for.

MIND_MAP_JSON_SYSTEM_PROMPT = (
    "You are Prepza AI, generating a mind map from a student's uploaded "
    "document for the Prepza study platform. Read the provided document "
    "text and produce a mind map as STRICT JSON ONLY - no markdown code "
    "fences, no preamble, no text before or after the JSON object. The "
    "JSON must have this exact shape:\n"
    '{"title": "string", "subtitle": "string", "center": "string", '
    '"branches": [{"id": "string", "label": "string"}]}\n\n'
    "Guidelines: \"center\" is the document's single core topic, in 2-4 "
    "words (e.g. \"Interest Theory\", \"Cellular Respiration\"). Produce "
    "4-8 \"branches\" - the main concepts/subtopics that radiate from the "
    "center, each with a short \"label\" (2-4 words) capturing one key "
    "idea from the material. \"id\" must be a short lowercase slug unique "
    "within the branches list (e.g. \"compound-interest\"), used for "
    "diagram rendering, not shown to the student directly. Choose "
    "branches that reflect the document's actual major sections/themes, "
    "not minor details - a student should recognize the document's "
    "structure at a glance from the branch labels alone. Do not invent "
    "content not present in the source text."
)


def _parse_mindmap_json(raw_text):
    """
    Parses the model's mind map JSON, tolerating stray markdown code
    fences. Raises ValueError on anything that doesn't match the
    expected shape - caller treats this as a failed generation, not a
    crash.
    """
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    data = json.loads(cleaned)

    if not isinstance(data, dict):
        raise ValueError("Mind map JSON root must be an object")
    if "title" not in data or "center" not in data or "branches" not in data:
        raise ValueError("Mind map JSON missing required 'title', 'center', or 'branches' key")
    if not isinstance(data["center"], str) or not data["center"].strip():
        raise ValueError("Mind map JSON 'center' must be a non-empty string")
    if not isinstance(data["branches"], list) or not data["branches"]:
        raise ValueError("Mind map JSON 'branches' must be a non-empty list")
    seen_ids = set()
    for branch in data["branches"]:
        if not isinstance(branch, dict) or "id" not in branch or "label" not in branch:
            raise ValueError("Each mind map branch must have 'id' and 'label'")
        if not isinstance(branch["id"], str) or not branch["id"].strip():
            raise ValueError("Each mind map branch 'id' must be a non-empty string")
        if not isinstance(branch["label"], str) or not branch["label"].strip():
            raise ValueError("Each mind map branch 'label' must be a non-empty string")
        if branch["id"] in seen_ids:
            raise ValueError(f"Duplicate mind map branch id: {branch['id']!r}")
        seen_ids.add(branch["id"])

    return data


def generate_document_mindmap(document_content_id, triggering_user_id, plan_tier="free", parameters=None):
    from ai_reusable_generation import generate_document_material
    return generate_document_material(
        material_type="mind_map",
        document_content_id=document_content_id,
        triggering_user_id=triggering_user_id,
        plan_tier=plan_tier,
        parameters=parameters,
    )

def _legacy_generate_document_mindmap(document_content_id, triggering_user_id, plan_tier="free"):
    """
    Full pipeline for generating (or reusing) a document's AI mind map.
    Identical shape to generate_document_flashcards() - see that
    function's docstring for the caching/limits/error semantics, which
    are the same here.

    Returns a dict: {payload: dict, material_id, reused, model_used}.
    Raises AIBudgetExceededError / AIRateLimitExceededError /
    AIProviderError - callers should catch these the same way the
    other document-material routes do.
    """
    from app import db, DocumentContent, GeneratedMaterial

    content = db.session.get(DocumentContent, document_content_id)
    if not content:
        raise ValueError(f"DocumentContent {document_content_id} not found")

    existing = GeneratedMaterial.query.filter_by(
        document_content_id=document_content_id, material_type="mind_map"
    ).first()

    if existing and existing.status == "ready" and existing.payload:
        log_usage(triggering_user_id, request_type="reuse")
        return {
            "payload": json.loads(existing.payload),
            "material_id": existing.id,
            "reused": True,
            "model_used": None,
        }

    if not content.extracted_text:
        raise AIProviderError(
            "This document's text hasn't finished processing yet - try again shortly."
        )

    if is_spend_cap_reached():
        raise AIBudgetExceededError(
            "Prepza AI has reached its monthly budget - fresh mind maps are paused, "
            "but existing mind maps are still available."
        )

    allowed, used, limit = check_daily_limit(triggering_user_id, plan_tier=plan_tier)
    if not allowed:
        raise AIRateLimitExceededError(
            f"You've used {used}/{limit} AI questions today - try again tomorrow."
        )

    material = existing or GeneratedMaterial(
        document_content_id=document_content_id, material_type="mind_map"
    )
    material.status = "generating"
    material.error_message = None
    if not existing:
        db.session.add(material)
    db.session.commit()

    user_message = (
        f"Document text ({content.page_count or '?'} pages):\n\n{content.extracted_text}"
    )

    try:
        ai_response = _call_with_continuation(
            task="MIND_MAP",
            system_prompt=MIND_MAP_JSON_SYSTEM_PROMPT,
            user_message=user_message,
        )
        parsed = _parse_mindmap_json(ai_response.text)
    except Exception as e:
        material.status = "failed"
        material.error_message = str(e)[:500]
        db.session.commit()
        if isinstance(e, (AIBudgetExceededError, AIRateLimitExceededError, AIProviderError)):
            raise
        raise AIProviderError(f"Mind map generation failed: {e}")

    log_usage(
        triggering_user_id,
        request_type="mind_map",
        model=ai_response.model_used,
        provider=ai_response.provider,
        usage=ai_response.usage,
    )

    material.payload = json.dumps(parsed)
    material.status = "ready"
    db.session.commit()

    return {
        "payload": parsed,
        "material_id": material.id,
        "reused": False,
        "model_used": ai_response.model_used,
    }
