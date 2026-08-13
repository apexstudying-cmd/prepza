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
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

import anthropic


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
        "primary": MODEL_HAIKU_4_5,
        "fallback": MODEL_SONNET_5,
        "max_tokens": 1536,
        "notes": "Condensed notes from a document.",
    },
    "FLASHCARDS": {
        "primary": MODEL_HAIKU_4_5,
        "fallback": MODEL_SONNET_5,
        "max_tokens": 2048,
        "notes": "Mechanical extraction of Q/A pairs from source text.",
    },
    "QUIZZES": {
        "primary": MODEL_SONNET_5,
        "fallback": None,
        "max_tokens": 2048,
        "notes": "Needs correct distractors/answers, not just plausible-looking ones.",
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
        "primary": MODEL_HAIKU_4_5,
        "fallback": MODEL_SONNET_5,
        "max_tokens": 1536,
        "notes": "Structural extraction (nodes/edges), not deep reasoning.",
    },
}


# ============================================================
# 3. PRICING (per MTok, USD) - keyed by effective date since Anthropic
#    has an announced Sonnet 5 price change on 2026-08-31.
#    Re-verify against platform.claude.com/docs if this drifts far
#    from today's date. Cache multipliers apply to the INPUT price only.
# ============================================================

_PRICING_SCHEDULE = {
    MODEL_SONNET_5: [
        # (effective_from, input_per_mtok, output_per_mtok)
        (datetime(2000, 1, 1), Decimal("2.00"), Decimal("10.00")),
        (datetime(2026, 8, 31), Decimal("3.00"), Decimal("15.00")),
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


def _get_provider():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    return AnthropicProvider(api_key), "anthropic"


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
            return AIResponse(
                text=text,
                model_used=model,
                provider=provider_name,
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
    Logs one row to ai_usage_log. `request_type` is 'answer' | 'reuse' |
    'summarize' (matches the existing column). For 'reuse' rows, model/
    provider stay None and usage stays zeroed - no API call was made.
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
# 7. GLOBAL SPEND CIRCUIT BREAKER (monthly)
# ============================================================

DEFAULT_MONTHLY_AI_BUDGET_USD = Decimal("20.00")
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


def _call_with_continuation(task, system_prompt, user_message, max_tokens=None):
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
            system=system_prompt,
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


def generate_document_summary(document_content_id, triggering_user_id, plan_tier="free"):
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
