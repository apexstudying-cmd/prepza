"""Reusable document-AI artifact orchestration.

This layer sits above the existing feature-specific generators. It gives each
feature a deterministic identity and a PostgreSQL concurrency boundary while
leaving the provider/parsing code in ai_service.py intact.

Student-facing callers deliberately receive the same result shape as the
existing generators and never receive a cache/reuse signal. A reuse is simply
an already-available result.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from ai_artifact_fingerprint import build_generation_fingerprint, GENERATION_VERSION
from ai_generation_store import (
    claim_or_get_generation,
    wait_for_generation,
    mark_generation_ready,
    mark_generation_failed,
)

PROMPT_VERSIONS = {
    "summary": "v1",
    "quiz": "v1",
    "flashcards": "v1",
    "podcast": "v1",
    "mind_map": "v1",
}

SCHEMA_VERSIONS = {
    "summary": "v1",
    "quiz": "v1",
    "flashcards": "v1",
    "podcast": "v1",
    "mind_map": "v1",
}

DEFAULT_PARAMETERS = {
    "summary": {"variant": "default"},
    "quiz": {"question_count": "model_default"},
    "flashcards": {"card_count": "model_default"},
    "podcast": {"duration": "model_default"},
    "mind_map": {"branch_count": "model_default"},
}


class AIArtifactInProgressError(Exception):
    """Raised only if a concurrent generation outlives the wait window."""


def _resolve_scope(document_content_id: int, user_id: int) -> tuple[str, int | None]:
    """Return shared only for content that has become approved public material.

    Ordinary student uploads remain private, even when DocumentContent byte
    deduplication points multiple users at the same content row. Once a
    document is approved for the public Prepza Library, its AI artifacts may
    become canonical shared material.
    """
    from app import db, Document, LibraryPublication

    published = (
        db.session.query(LibraryPublication.id)
        .join(Document, Document.id == LibraryPublication.document_id)
        .filter(
            Document.document_content_id == document_content_id,
            LibraryPublication.status == "approved",
        )
        .first()
    )
    if published:
        return "shared", None
    return "private", int(user_id)


def _lookup_artifact(fingerprint: str):
    from sqlalchemy import text
    from app import db

    return db.session.execute(
        text(
            """
            SELECT id, status, payload
            FROM ai_generation_artifact
            WHERE fingerprint = :fingerprint
            """
        ),
        {"fingerprint": fingerprint},
    ).mappings().first()


def _material_for_fingerprint(fingerprint: str):
    from app import GeneratedMaterial
    return GeneratedMaterial.query.filter_by(generation_fingerprint=fingerprint).first()


def _ensure_material(
    *,
    document_content_id: int,
    material_type: str,
    fingerprint: str,
    parameters: dict[str, Any],
    generation_version: str,
    scope: str,
    owner_user_id: int | None,
    payload: dict[str, Any],
    status: str = "ready",
):
    """Create/update the document-facing GeneratedMaterial attachment."""
    from sqlalchemy.exc import IntegrityError
    from app import db, GeneratedMaterial

    material = _material_for_fingerprint(fingerprint)
    if material:
        material.payload = json.dumps(payload, ensure_ascii=False)
        material.status = status
        material.error_message = None
        db.session.commit()
        return material

    material = GeneratedMaterial(
        document_content_id=document_content_id,
        material_type=material_type,
        status=status,
        payload=json.dumps(payload, ensure_ascii=False) if payload is not None else None,
        generation_fingerprint=fingerprint,
        generation_parameters=parameters,
        generation_version=generation_version,
        scope=scope,
        owner_user_id=owner_user_id,
    )
    db.session.add(material)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        material = _material_for_fingerprint(fingerprint)
        if not material:
            raise
    return material


def _reset_material_for_generation(material) -> None:
    from app import db
    if material:
        material.status = "generating"
        material.error_message = None
        material.payload = None
        db.session.commit()


def get_material_for_document(document_id: int, user_id: int, material_type: str):
    """Resolve the current authorized material for document-facing routes."""
    from app import db, Document, DocumentContent

    document = db.session.get(Document, document_id)
    if not document or document.user_id != user_id or document.is_removed:
        return None
    if not document.document_content_id:
        return None
    content = db.session.get(DocumentContent, document.document_content_id)
    if not content:
        return None

    scope, owner_user_id = _resolve_scope(content.id, user_id)
    params = dict(DEFAULT_PARAMETERS[material_type])
    fingerprint = build_generation_fingerprint(
        content_hash=content.content_hash,
        material_type=material_type,
        parameters=params,
        prompt_version=PROMPT_VERSIONS[material_type],
        schema_version=SCHEMA_VERSIONS[material_type],
        scope=scope,
        owner_user_id=owner_user_id,
    )
    material = _material_for_fingerprint(fingerprint)
    if material and material.status == "ready":
        return material
    return None


def generate_reusable_document_material(
    *,
    material_type: str,
    document_content_id: int,
    triggering_user_id: int,
    plan_tier: str,
    legacy_generator: Callable[..., dict[str, Any]],
    request_type: str,
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one feature through deterministic identity + concurrency reuse."""
    from app import db, DocumentContent, AiJob
    from ai_service import is_spend_cap_reached, check_daily_limit
    from ai_service import AIBudgetExceededError, AIRateLimitExceededError, AIProviderError

    content = db.session.get(DocumentContent, document_content_id)
    if not content:
        raise ValueError(f"DocumentContent {document_content_id} not found")
    if not content.extracted_text:
        raise AIProviderError(
            "This document's text hasn't finished processing yet - try again shortly."
        )

    params = dict(DEFAULT_PARAMETERS[material_type])
    if parameters:
        params.update(parameters)

    scope, owner_user_id = _resolve_scope(document_content_id, triggering_user_id)
    fingerprint = build_generation_fingerprint(
        content_hash=content.content_hash,
        material_type=material_type,
        parameters=params,
        prompt_version=PROMPT_VERSIONS[material_type],
        schema_version=SCHEMA_VERSIONS[material_type],
        scope=scope,
        owner_user_id=owner_user_id,
    )

    existing = _lookup_artifact(fingerprint)
    if existing and existing["status"] == "ready" and existing["payload"]:
        payload = existing["payload"]
        material = _ensure_material(
            document_content_id=document_content_id,
            material_type=material_type,
            fingerprint=fingerprint,
            parameters=params,
            generation_version=GENERATION_VERSION,
            scope=scope,
            owner_user_id=owner_user_id,
            payload=payload,
        )
        # Keep the existing usage semantics: reuse rows are explicitly
        # excluded from the fresh-generation counter and carry zero cost.
        from ai_service import log_usage
        log_usage(triggering_user_id, request_type="reuse")
        return {"payload": payload, "material_id": material.id, "reused": False, "model_used": None}

    if existing and existing["status"] == "generating":
        waited = wait_for_generation(fingerprint, timeout_seconds=45.0)
        if waited.status == "ready" and waited.payload:
            material = _ensure_material(
                document_content_id=document_content_id,
                material_type=material_type,
                fingerprint=fingerprint,
                parameters=params,
                generation_version=GENERATION_VERSION,
                scope=scope,
                owner_user_id=owner_user_id,
                payload=waited.payload,
            )
            from ai_service import log_usage
            log_usage(triggering_user_id, request_type="reuse")
            return {"payload": waited.payload, "material_id": material.id, "reused": False, "model_used": None}
        if waited.status == "failed":
            existing = None
        else:
            raise AIArtifactInProgressError("AI generation is still in progress; try again shortly.")

    # Only a request that is actually going to own a fresh generation reaches
    # entitlement checks. Reuses above never consume the fresh-generation pool.
    if is_spend_cap_reached():
        raise AIBudgetExceededError(
            f"Prepza AI has reached its monthly budget - fresh {material_type.replace('_', ' ')} generation is paused, but existing material is still available."
        )

    allowed, used, limit = check_daily_limit(triggering_user_id, plan_tier=plan_tier)
    if not allowed:
        raise AIRateLimitExceededError(
            f"You've used {used}/{limit} AI questions today - try again tomorrow."
        )

    claim = claim_or_get_generation(
        fingerprint=fingerprint,
        content_hash=content.content_hash,
        feature=material_type,
        parameters=params,
        prompt_version=PROMPT_VERSIONS[material_type],
        schema_version=SCHEMA_VERSIONS[material_type],
        scope=scope,
        owner_user_id=owner_user_id,
    )

    if not claim.owner:
        if claim.status == "ready" and claim.payload:
            material = _ensure_material(
                document_content_id=document_content_id,
                material_type=material_type,
                fingerprint=fingerprint,
                parameters=params,
                generation_version=GENERATION_VERSION,
                scope=scope,
                owner_user_id=owner_user_id,
                payload=claim.payload,
            )
            from ai_service import log_usage
            log_usage(triggering_user_id, request_type="reuse")
            return {"payload": claim.payload, "material_id": material.id, "reused": False, "model_used": None}
        waited = wait_for_generation(fingerprint, timeout_seconds=45.0)
        if waited.status == "ready" and waited.payload:
            material = _ensure_material(
                document_content_id=document_content_id,
                material_type=material_type,
                fingerprint=fingerprint,
                parameters=params,
                generation_version=GENERATION_VERSION,
                scope=scope,
                owner_user_id=owner_user_id,
                payload=waited.payload,
            )
            from ai_service import log_usage
            log_usage(triggering_user_id, request_type="reuse")
            return {"payload": waited.payload, "material_id": material.id, "reused": False, "model_used": None}
        raise AIArtifactInProgressError("AI generation is still in progress; try again shortly.")

    material = _material_for_fingerprint(fingerprint)
    if material:
        _reset_material_for_generation(material)
    else:
        material = _ensure_material(
            document_content_id=document_content_id,
            material_type=material_type,
            fingerprint=fingerprint,
            parameters=params,
            generation_version=GENERATION_VERSION,
            scope=scope,
            owner_user_id=owner_user_id,
            payload={},
            status="generating",
        )

    job = AiJob(
        document_content_id=document_content_id,
        feature=material_type,
        status="processing",
    )
    db.session.add(job)
    db.session.commit()

    try:
        result = legacy_generator(
            document_content_id=document_content_id,
            triggering_user_id=triggering_user_id,
            plan_tier=plan_tier,
            generation_fingerprint=fingerprint,
            generation_parameters=params,
            generation_version=GENERATION_VERSION,
            scope=scope,
            owner_user_id=owner_user_id,
        )
        payload = result["payload"]
        mark_generation_ready(claim.artifact_id, payload)
        job.status = "completed"
        job.completed_at = __import__("datetime").datetime.utcnow()
        db.session.commit()
        return {"payload": payload, "material_id": result["material_id"], "reused": False, "model_used": result.get("model_used")}
    except Exception as exc:
        mark_generation_failed(claim.artifact_id, str(exc))
        job.status = "failed"
        job.completed_at = __import__("datetime").datetime.utcnow()
        job.error_message = str(exc)[:500]
        db.session.commit()
        raise
