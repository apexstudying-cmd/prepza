"""Reusable, privacy-aware AI document artifact generation."""
from __future__ import annotations

import json
from datetime import datetime

from ai_artifact_fingerprint import GENERATION_VERSION, build_generation_fingerprint
from ai_generation_store import (
    claim_or_get_generation,
    mark_generation_failed,
    mark_generation_ready,
    wait_for_generation,
)

PROMPT_VERSIONS = {key: f"{key}-v2" for key in ("summary", "quiz", "flashcards", "podcast", "mind_map")}
SCHEMA_VERSIONS = {key: f"schema-v2" for key in PROMPT_VERSIONS}
PARAMETER_KEYS = {
    "summary": {"max_pages", "style", "language"},
    "quiz": {"question_count", "difficulty", "language"},
    "flashcards": {"card_count", "difficulty", "language"},
    "podcast": {"duration_minutes", "style", "language"},
    "mind_map": {"node_count", "language"},
}


def normalize_parameters(material_type: str, parameters: dict | None) -> dict:
    params = parameters or {}
    if not isinstance(params, dict):
        raise ValueError("AI generation parameters must be an object")
    unknown = set(params) - PARAMETER_KEYS[material_type]
    if unknown:
        raise ValueError(f"Unsupported {material_type} parameter(s): {', '.join(sorted(unknown))}")
    normalized = {}
    for key in sorted(params):
        value = params[key]
        if key in {"max_pages", "question_count", "card_count", "duration_minutes", "node_count"}:
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{key} must be a positive integer")
            normalized[key] = value
        else:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{key} must be a non-empty string")
            normalized[key] = " ".join(value.split())
    return normalized


def _content_scope(document_content_id: int, triggering_user_id: int) -> tuple[str, int | None]:
    """Resolve scope from the actual document relationship, not content bytes alone."""
    from app import db, Document, LibraryPublication

    owned = (
        db.session.query(Document.id)
        .filter(
            Document.user_id == triggering_user_id,
            Document.document_content_id == document_content_id,
            Document.is_removed.is_(False),
        )
        .first()
    )
    if owned:
        approved = (
            db.session.query(LibraryPublication.id)
            .filter(
                LibraryPublication.document_id == owned.id,
                LibraryPublication.status == "approved",
            )
            .first()
        )
        if approved:
            return "shared", None
        return "private", int(triggering_user_id)

    public = (
        db.session.query(LibraryPublication.id)
        .join(Document, LibraryPublication.document_id == Document.id)
        .filter(
            Document.document_content_id == document_content_id,
            LibraryPublication.status == "approved",
        )
        .first()
    )
    if public:
        return "shared", None
    raise PermissionError("You do not have access to this document")


def _parameter_instruction(params: dict) -> str:
    if not params:
        return ""
    labels = {
        "max_pages": "summary target length",
        "question_count": "number of quiz questions",
        "card_count": "number of flashcards",
        "duration_minutes": "target podcast duration in minutes",
        "node_count": "number of mind-map nodes/branches",
        "difficulty": "difficulty",
        "style": "style",
        "language": "language",
    }
    return "Generation constraints (follow these exactly):\n" + "\n".join(
        f"- {labels.get(k, k)}: {params[k]}" for k in sorted(params)
    )


def _generator(material_type):
    import ai_service
    specs = {
        "summary": (ai_service.SUMMARY_JSON_SYSTEM_PROMPT, ai_service._parse_summary_json, "SUMMARIZATION"),
        "quiz": (ai_service.QUIZ_JSON_SYSTEM_PROMPT, ai_service._parse_quiz_json, "QUIZZES"),
        "flashcards": (ai_service.FLASHCARDS_JSON_SYSTEM_PROMPT, ai_service._parse_flashcards_json, "FLASHCARDS"),
        "podcast": (ai_service.PODCAST_SCRIPT_JSON_SYSTEM_PROMPT, ai_service._parse_podcast_script_json, "PODCAST_SCRIPT"),
        "mind_map": (ai_service.MIND_MAP_JSON_SYSTEM_PROMPT, ai_service._parse_mindmap_json, "MIND_MAP"),
    }
    return specs[material_type]


def _material_from_payload(*, document_content_id, material_type, fingerprint, payload, scope, owner_user_id, parameters):
    from app import db, GeneratedMaterial
    from sqlalchemy.exc import IntegrityError

    material = GeneratedMaterial.query.filter_by(generation_fingerprint=fingerprint).first()
    if material:
        return material
    material = GeneratedMaterial(
        document_content_id=document_content_id,
        material_type=material_type,
        status="ready",
        payload=json.dumps(payload, ensure_ascii=False),
        generation_fingerprint=fingerprint,
        generation_parameters=parameters,
        generation_version=GENERATION_VERSION,
        scope=scope,
        owner_user_id=owner_user_id,
    )
    db.session.add(material)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        material = GeneratedMaterial.query.filter_by(generation_fingerprint=fingerprint).first()
        if not material:
            raise
    return material


def _podcast_payload(parsed):
    return {"script": parsed, "audio_status": "pending", "audio_storage_path": None, "duration_seconds": None}


def generate_document_material(*, material_type, document_content_id, triggering_user_id, plan_tier="free", parameters=None):
    import ai_service
    from app import db, DocumentContent, AiJob

    if material_type not in PROMPT_VERSIONS:
        raise ValueError(f"Unsupported AI material type: {material_type}")
    params = normalize_parameters(material_type, parameters)
    content = db.session.get(DocumentContent, document_content_id)
    if not content:
        raise ValueError(f"DocumentContent {document_content_id} not found")
    if not content.extracted_text:
        raise ai_service.AIProviderError("This document's text hasn't finished processing yet - try again shortly.")

    scope, owner_user_id = _content_scope(document_content_id, triggering_user_id)
    prompt_version = PROMPT_VERSIONS[material_type]
    schema_version = SCHEMA_VERSIONS[material_type]
    fingerprint = build_generation_fingerprint(
        content_hash=content.content_hash,
        material_type=material_type,
        parameters=params,
        prompt_version=prompt_version,
        schema_version=schema_version,
        scope=scope,
        owner_user_id=owner_user_id,
    )

    lookup = claim_or_get_generation(
        fingerprint=fingerprint,
        content_hash=content.content_hash,
        feature=material_type,
        parameters=params,
        prompt_version=prompt_version,
        schema_version=schema_version,
        scope=scope,
        owner_user_id=owner_user_id,
    )
    if lookup.status == "ready" and lookup.payload:
        material = _material_from_payload(
            document_content_id=document_content_id,
            material_type=material_type,
            fingerprint=fingerprint,
            payload=lookup.payload,
            scope=scope,
            owner_user_id=owner_user_id,
            parameters=params,
        )
        return {"payload": lookup.payload, "material_id": material.id, "reused": True, "model_used": None}

    if not lookup.owner:
        waited = wait_for_generation(fingerprint)
        if waited.status == "ready" and waited.payload:
            material = _material_from_payload(
                document_content_id=document_content_id,
                material_type=material_type,
                fingerprint=fingerprint,
                payload=waited.payload,
                scope=scope,
                owner_user_id=owner_user_id,
                parameters=params,
            )
            return {"payload": waited.payload, "material_id": material.id, "reused": True, "model_used": None}
        if waited.status == "failed":
            raise ai_service.AIProviderError("AI generation failed - please try again.")
        raise ai_service.AIProviderError("This material is still being prepared - please try again shortly.")

    job = None
    try:
        if ai_service.is_spend_cap_reached():
            raise ai_service.AIBudgetExceededError(
                f"Prepza AI has reached its monthly budget - fresh {material_type} generation is paused, but existing material is still available."
            )
        allowed, used, limit = ai_service.check_daily_limit(triggering_user_id, plan_tier=plan_tier)
        if not allowed:
            raise ai_service.AIRateLimitExceededError(
                f"You've used {used}/{limit} AI generations today - try again tomorrow."
            )

        job = AiJob(
            document_content_id=document_content_id,
            feature=material_type,
            status="processing",
            started_at=datetime.utcnow(),
        )
        db.session.add(job)
        db.session.commit()

        system_prompt, parser, task = _generator(material_type)
        user_message = f"Document text ({content.page_count or '?'} pages):\n\n{content.extracted_text}"
        constraint = _parameter_instruction(params)
        if constraint:
            user_message = constraint + "\n\n" + user_message
        ai_response = ai_service._call_with_continuation(
            task=task,
            system_prompt=system_prompt,
            user_message=user_message,
        )
        parsed = parser(ai_response.text)
        payload = _podcast_payload(parsed) if material_type == "podcast" else parsed
        ai_service.log_usage(
            triggering_user_id,
            request_type=material_type,
            model=ai_response.model_used,
            provider=ai_response.provider,
            usage=ai_response.usage,
        )
        mark_generation_ready(lookup.artifact_id, payload)
        job.status, job.completed_at = "completed", datetime.utcnow()
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        try:
            mark_generation_failed(lookup.artifact_id, str(exc))
        except Exception:
            db.session.rollback()
        if job is not None:
            try:
                job.status, job.error_message, job.completed_at = "failed", str(exc)[:500], datetime.utcnow()
                db.session.commit()
            except Exception:
                db.session.rollback()
        if isinstance(exc, (ai_service.AIBudgetExceededError, ai_service.AIRateLimitExceededError, ai_service.AIProviderError)):
            raise
        raise ai_service.AIProviderError(f"{material_type} generation failed: {exc}")

    material = _material_from_payload(
        document_content_id=document_content_id,
        material_type=material_type,
        fingerprint=fingerprint,
        payload=payload,
        scope=scope,
        owner_user_id=owner_user_id,
        parameters=params,
    )
    return {"payload": payload, "material_id": material.id, "reused": False, "model_used": ai_response.model_used}
