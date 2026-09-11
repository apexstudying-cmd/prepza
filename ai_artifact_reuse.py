"""Deterministic, concurrency-safe orchestration for reusable document AI.

Feature-specific generators remain the provider/parsing implementation. This
module owns the reusable identity, privacy scope, atomic claim, waiting, and
canonical artifact lifecycle.
"""
from __future__ import annotations

from datetime import datetime
import json
from typing import Any, Callable

from ai_artifact_fingerprint import GENERATION_VERSION, build_generation_fingerprint
from ai_generation_store import (
    claim_or_get_generation,
    mark_generation_failed,
    mark_generation_ready,
    wait_for_generation,
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
    """A concurrent generation did not finish within the request wait window."""


def resolve_generation_scope(document_content_id: int, user_id: int) -> tuple[str, int | None]:
    """Shared only for explicitly approved public-library material.

    Byte-identical private uploads remain private; DocumentContent's own
    deduplication must never turn that into cross-user AI sharing.
    """
    from app import db, Document, LibraryPublication

    approved = (
        db.session.query(LibraryPublication.id)
        .join(Document, Document.id == LibraryPublication.document_id)
        .filter(
            Document.document_content_id == document_content_id,
            LibraryPublication.status == "approved",
        )
        .first()
    )
    return ("shared", None) if approved else ("private", int(user_id))


def _artifact_payload(row):
    payload = row["payload"] if row else None
    if isinstance(payload, str):
        return json.loads(payload)
    return payload


def _find_material(fingerprint: str):
    from app import GeneratedMaterial
    return GeneratedMaterial.query.filter_by(generation_fingerprint=fingerprint).first()


def _attach_material(
    *, document_content_id: int,
    material_type: str,
    fingerprint: str,
    parameters: dict[str, Any],
    scope: str,
    owner_user_id: int | None,
    payload: dict[str, Any],
    status: str = "ready",
):
    from sqlalchemy.exc import IntegrityError
    from app import db, GeneratedMaterial

    material = _find_material(fingerprint)
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
        material = _find_material(fingerprint)
        if not material:
            raise
    return material


def _prepare_material(material, *, parameters, fingerprint, scope, owner_user_id):
    from app import db
    material.generation_fingerprint = fingerprint
    material.generation_parameters = parameters
    material.generation_version = GENERATION_VERSION
    material.scope = scope
    material.owner_user_id = owner_user_id
    material.status = "generating"
    material.error_message = None
    material.payload = None
    db.session.commit()


def _create_ai_job(document_content_id, feature):
    from app import db, AiJob
    job = AiJob(
        document_content_id=document_content_id,
        feature=feature,
        status="processing",
        started_at=datetime.utcnow(),
    )
    db.session.add(job)
    db.session.commit()
    return job


def _finish_ai_job(job, success: bool, error: str | None = None):
    from app import db
    job.status = "completed" if success else "failed"
    job.completed_at = datetime.utcnow()
    if error:
        job.error_message = str(error)[:500]
    db.session.commit()


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
    """Wrap an existing generator without changing its provider/parsing logic."""
    from app import db, DocumentContent
    from ai_service import (
        AIBudgetExceededError,
        AIRateLimitExceededError,
        AIProviderError,
        check_daily_limit,
        is_spend_cap_reached,
        log_usage,
    )

    if material_type not in DEFAULT_PARAMETERS:
        raise ValueError(f"Unsupported reusable material type: {material_type}")

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

    scope, owner_user_id = resolve_generation_scope(document_content_id, triggering_user_id)
    fingerprint = build_generation_fingerprint(
        content_hash=content.content_hash,
        material_type=material_type,
        parameters=params,
        prompt_version=PROMPT_VERSIONS[material_type],
        schema_version=SCHEMA_VERSIONS[material_type],
        scope=scope,
        owner_user_id=owner_user_id,
    )

    # Fast path before any fresh-generation entitlement checks.
    existing = __import__("ai_generation_store").ai_generation_store._lookup_generation_row(fingerprint)
    if existing and existing.status == "ready" and existing.payload:
        payload = existing.payload
        material = _attach_material(
            document_content_id=document_content_id,
            material_type=material_type,
            fingerprint=fingerprint,
            parameters=params,
            scope=scope,
            owner_user_id=owner_user_id,
            payload=payload,
        )
        log_usage(triggering_user_id, request_type="reuse")
        return {"payload": payload, "material_id": material.id, "reused": False, "model_used": None}

    if existing and existing.status == "generating":
        waited = wait_for_generation(fingerprint, timeout_seconds=45.0)
        if waited.status == "ready" and waited.payload:
            payload = waited.payload
            material = _attach_material(
                document_content_id=document_content_id,
                material_type=material_type,
                fingerprint=fingerprint,
                parameters=params,
                scope=scope,
                owner_user_id=owner_user_id,
                payload=payload,
            )
            log_usage(triggering_user_id, request_type="reuse")
            return {"payload": payload, "material_id": material.id, "reused": False, "model_used": None}
        if waited.status != "failed":
            raise AIArtifactInProgressError("AI generation is still in progress; try again shortly.")

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
        waited = wait_for_generation(fingerprint, timeout_seconds=45.0)
        if waited.status == "ready" and waited.payload:
            payload = waited.payload
            material = _attach_material(
                document_content_id=document_content_id,
                material_type=material_type,
                fingerprint=fingerprint,
                parameters=params,
                scope=scope,
                owner_user_id=owner_user_id,
                payload=payload,
            )
            log_usage(triggering_user_id, request_type="reuse")
            return {"payload": payload, "material_id": material.id, "reused": False, "model_used": None}
        raise AIArtifactInProgressError("AI generation is still in progress; try again shortly.")

    material = _find_material(fingerprint)
    if material:
        _prepare_material(
            material,
            parameters=params,
            fingerprint=fingerprint,
            scope=scope,
            owner_user_id=owner_user_id,
        )
    else:
        material = _attach_material(
            document_content_id=document_content_id,
            material_type=material_type,
            fingerprint=fingerprint,
            parameters=params,
            scope=scope,
            owner_user_id=owner_user_id,
            payload={},
            status="generating",
        )

    job = _create_ai_job(document_content_id, material_type)
    try:
        # The legacy generator now sees the generating GeneratedMaterial row,
        # so it performs the existing provider/parsing work without creating a
        # second material row. No provider code is duplicated here.
        result = legacy_generator(
            document_content_id=document_content_id,
            triggering_user_id=triggering_user_id,
            plan_tier=plan_tier,
        )
        payload = result["payload"]
        material = db.session.get(type(material), result["material_id"]) or material
        material.generation_fingerprint = fingerprint
        material.generation_parameters = params
        material.generation_version = GENERATION_VERSION
        material.scope = scope
        material.owner_user_id = owner_user_id
        material.payload = json.dumps(payload, ensure_ascii=False)
        material.status = "ready"
        db.session.commit()
        mark_generation_ready(claim.artifact_id, payload)
        _finish_ai_job(job, True)
        return {"payload": payload, "material_id": material.id, "reused": False, "model_used": result.get("model_used")}
    except Exception as exc:
        try:
            mark_generation_failed(claim.artifact_id, str(exc))
        finally:
            _finish_ai_job(job, False, str(exc))
        raise
