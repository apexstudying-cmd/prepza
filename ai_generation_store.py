"""Persistence primitives for fingerprinted AI artifact generation.

This module deliberately contains no provider calls and no student-facing UX.
It owns the concurrency boundary used by generation features: a unique
fingerprint means concurrent requests for the same artifact can share one
in-flight generation instead of issuing duplicate provider calls.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GenerationLookup:
    artifact_id: int
    status: str
    payload: dict[str, Any] | None
    owner: bool


def claim_or_get_generation(
    *,
    fingerprint: str,
    content_hash: str,
    feature: str,
    parameters: dict[str, Any] | None,
    prompt_version: str,
    schema_version: str,
    scope: str = "shared",
    owner_user_id: int | None = None,
) -> GenerationLookup:
    """Atomically claim a missing/failed fingerprint or observe its state.

    The database UNIQUE constraint is the concurrency primitive. The first
    request inserts the row and becomes the owner. A simultaneous request
    observes the existing GENERATING row and attaches to it instead of making
    another provider request. FAILED rows may be claimed again.

    Scope/owner are persisted as well as encoded into the fingerprint. This
    gives the database a second invariant against accidentally exposing a
    private artifact through a shared generation path.
    """
    from sqlalchemy import text
    from app import db

    normalized_scope = str(scope).strip().lower()
    if normalized_scope not in {"shared", "private"}:
        raise ValueError("scope must be 'shared' or 'private'")
    if normalized_scope == "private" and owner_user_id is None:
        raise ValueError("private artifacts require owner_user_id")
    if normalized_scope == "shared" and owner_user_id is not None:
        raise ValueError("shared artifacts must not include owner_user_id")

    parameters_json = json.dumps(parameters or {}, sort_keys=True, separators=(",", ":"))

    inserted = db.session.execute(
        text(
            """
            INSERT INTO ai_generation_artifact
                (fingerprint, content_hash, feature, parameters,
                 prompt_version, schema_version, scope, owner_user_id, status)
            VALUES
                (:fingerprint, :content_hash, :feature, CAST(:parameters AS jsonb),
                 :prompt_version, :schema_version, :scope, :owner_user_id, 'generating')
            ON CONFLICT (fingerprint) DO NOTHING
            RETURNING id, status, payload
            """
        ),
        {
            "fingerprint": fingerprint,
            "content_hash": content_hash,
            "feature": feature,
            "parameters": parameters_json,
            "prompt_version": prompt_version,
            "schema_version": schema_version,
            "scope": normalized_scope,
            "owner_user_id": owner_user_id,
        },
    ).mappings().first()

    if inserted is not None:
        db.session.commit()
        return GenerationLookup(
            artifact_id=int(inserted["id"]),
            status=inserted["status"],
            payload=inserted["payload"],
            owner=True,
        )

    existing = db.session.execute(
        text(
            """
            SELECT id, status, payload, scope, owner_user_id
            FROM ai_generation_artifact
            WHERE fingerprint = :fingerprint
            """
        ),
        {"fingerprint": fingerprint},
    ).mappings().first()

    if existing is None:
        # Defensive retry for an unusual concurrent delete/rollback window.
        db.session.rollback()
        return claim_or_get_generation(
            fingerprint=fingerprint,
            content_hash=content_hash,
            feature=feature,
            parameters=parameters,
            prompt_version=prompt_version,
            schema_version=schema_version,
            scope=normalized_scope,
            owner_user_id=owner_user_id,
        )

    # A fingerprint collision should be impossible because scope/owner are
    # part of the fingerprint. Refuse to attach if persisted identity disagrees.
    if existing["scope"] != normalized_scope or existing["owner_user_id"] != owner_user_id:
        raise RuntimeError("AI artifact fingerprint ownership mismatch")

    if existing["status"] == "failed":
        reclaimed = db.session.execute(
            text(
                """
                UPDATE ai_generation_artifact
                SET status = 'generating',
                    error_message = NULL,
                    payload = NULL,
                    updated_at = CURRENT_TIMESTAMP,
                    completed_at = NULL
                WHERE fingerprint = :fingerprint
                  AND status = 'failed'
                RETURNING id, status, payload
                """
            ),
            {"fingerprint": fingerprint},
        ).mappings().first()
        db.session.commit()
        if reclaimed is not None:
            return GenerationLookup(
                artifact_id=int(reclaimed["id"]),
                status="generating",
                payload=None,
                owner=True,
            )

    return GenerationLookup(
        artifact_id=int(existing["id"]),
        status=existing["status"],
        payload=existing["payload"],
        owner=False,
    )


def wait_for_generation(
    fingerprint: str,
    *,
    timeout_seconds: float = 30.0,
    poll_interval_seconds: float = 0.25,
) -> GenerationLookup:
    """Wait for an already-running generation without starting another one."""
    from sqlalchemy import text
    from app import db

    deadline = time.monotonic() + timeout_seconds
    while True:
        row = db.session.execute(
            text(
                """
                SELECT id, status, payload
                FROM ai_generation_artifact
                WHERE fingerprint = :fingerprint
                """
            ),
            {"fingerprint": fingerprint},
        ).mappings().first()

        if row is None:
            raise RuntimeError("AI generation artifact disappeared while waiting")

        if row["status"] != "generating":
            return GenerationLookup(
                artifact_id=int(row["id"]),
                status=row["status"],
                payload=row["payload"],
                owner=False,
            )

        if time.monotonic() >= deadline:
            return GenerationLookup(
                artifact_id=int(row["id"]),
                status="generating",
                payload=None,
                owner=False,
            )

        db.session.expire_all()
        time.sleep(poll_interval_seconds)


def mark_generation_ready(artifact_id: int, payload: dict[str, Any]) -> None:
    """Publish the completed artifact after the provider call succeeds."""
    from sqlalchemy import text
    from app import db

    db.session.execute(
        text(
            """
            UPDATE ai_generation_artifact
            SET status = 'ready',
                payload = CAST(:payload AS jsonb),
                error_message = NULL,
                updated_at = CURRENT_TIMESTAMP,
                completed_at = CURRENT_TIMESTAMP
            WHERE id = :artifact_id
            """
        ),
        {
            "artifact_id": artifact_id,
            "payload": json.dumps(payload, ensure_ascii=False),
        },
    )
    db.session.commit()


def mark_generation_failed(artifact_id: int, error_message: str) -> None:
    """Release an in-flight fingerprint after a provider/generation failure."""
    from sqlalchemy import text
    from app import db

    db.session.execute(
        text(
            """
            UPDATE ai_generation_artifact
            SET status = 'failed',
                error_message = :error_message,
                updated_at = CURRENT_TIMESTAMP,
                completed_at = CURRENT_TIMESTAMP
            WHERE id = :artifact_id
            """
        ),
        {"artifact_id": artifact_id, "error_message": error_message[:4000]},
    )
    db.session.commit()
