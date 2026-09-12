"""Persistence primitives for fingerprinted AI artifact generation."""

from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass
from typing import Any


GENERATION_LEASE_SECONDS = 15 * 60


@dataclass(frozen=True)
class GenerationLookup:
    artifact_id: int
    status: str
    payload: dict[str, Any] | None
    owner: bool
    lease_token: str | None = None


def _new_lease_token() -> str:
    return secrets.token_hex(32)


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
    """Atomically claim a fingerprint, with a fenced lease for its owner."""
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
    lease_token = _new_lease_token()

    inserted = db.session.execute(
        text(
            """
            INSERT INTO ai_generation_artifact
                (fingerprint, content_hash, feature, parameters,
                 prompt_version, schema_version, scope, owner_user_id,
                 status, lease_token)
            VALUES
                (:fingerprint, :content_hash, :feature, CAST(:parameters AS jsonb),
                 :prompt_version, :schema_version, :scope, :owner_user_id,
                 'generating', :lease_token)
            ON CONFLICT (fingerprint) DO NOTHING
            RETURNING id, status, payload, lease_token
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
            "lease_token": lease_token,
        },
    ).mappings().first()

    if inserted is not None:
        db.session.commit()
        return GenerationLookup(int(inserted["id"]), inserted["status"], inserted["payload"], True, inserted["lease_token"])

    existing = db.session.execute(
        text(
            """
            SELECT id, status, payload, scope, owner_user_id, updated_at, lease_token
            FROM ai_generation_artifact
            WHERE fingerprint = :fingerprint
            """
        ),
        {"fingerprint": fingerprint},
    ).mappings().first()

    if existing is None:
        db.session.rollback()
        return claim_or_get_generation(
            fingerprint=fingerprint, content_hash=content_hash, feature=feature,
            parameters=parameters, prompt_version=prompt_version,
            schema_version=schema_version, scope=normalized_scope,
            owner_user_id=owner_user_id,
        )

    if existing["scope"] != normalized_scope or existing["owner_user_id"] != owner_user_id:
        raise RuntimeError("AI artifact fingerprint ownership mismatch")

    if existing["status"] == "failed":
        reclaimed = db.session.execute(
            text(
                """
                UPDATE ai_generation_artifact
                SET status = 'generating', error_message = NULL, payload = NULL,
                    updated_at = CURRENT_TIMESTAMP, completed_at = NULL,
                    lease_token = :lease_token
                WHERE fingerprint = :fingerprint AND status = 'failed'
                RETURNING id, status, payload, lease_token
                """
            ),
            {"fingerprint": fingerprint, "lease_token": lease_token},
        ).mappings().first()
        db.session.commit()
        if reclaimed is not None:
            return GenerationLookup(int(reclaimed["id"]), "generating", None, True, reclaimed["lease_token"])

    if existing["status"] == "generating":
        reclaimed = db.session.execute(
            text(
                """
                UPDATE ai_generation_artifact
                SET updated_at = CURRENT_TIMESTAMP, error_message = NULL,
                    payload = NULL, completed_at = NULL, lease_token = :lease_token
                WHERE fingerprint = :fingerprint
                  AND status = 'generating'
                  AND updated_at < CURRENT_TIMESTAMP - (:lease_seconds * INTERVAL '1 second')
                RETURNING id, status, payload, lease_token
                """
            ),
            {"fingerprint": fingerprint, "lease_seconds": GENERATION_LEASE_SECONDS, "lease_token": lease_token},
        ).mappings().first()
        if reclaimed is not None:
            db.session.commit()
            return GenerationLookup(int(reclaimed["id"]), "generating", None, True, reclaimed["lease_token"])
        db.session.rollback()

    return GenerationLookup(int(existing["id"]), existing["status"], existing["payload"], False, None)


def wait_for_generation(fingerprint: str, *, timeout_seconds: float = 30.0, poll_interval_seconds: float = 0.25) -> GenerationLookup:
    from sqlalchemy import text
    from app import db

    deadline = time.monotonic() + timeout_seconds
    while True:
        row = db.session.execute(
            text("SELECT id, status, payload FROM ai_generation_artifact WHERE fingerprint = :fingerprint"),
            {"fingerprint": fingerprint},
        ).mappings().first()
        if row is None:
            raise RuntimeError("AI generation artifact disappeared while waiting")
        if row["status"] != "generating":
            return GenerationLookup(int(row["id"]), row["status"], row["payload"], False, None)
        if time.monotonic() >= deadline:
            return GenerationLookup(int(row["id"]), "generating", None, False, None)
        db.session.expire_all()
        time.sleep(poll_interval_seconds)


def mark_generation_ready(artifact_id: int, payload: dict[str, Any], lease_token: str | None = None) -> None:
    from sqlalchemy import text
    from app import db
    if not lease_token:
        raise ValueError("lease_token is required to publish an AI generation")
    result = db.session.execute(
        text(
            """
            UPDATE ai_generation_artifact
            SET status = 'ready', payload = CAST(:payload AS jsonb), error_message = NULL,
                updated_at = CURRENT_TIMESTAMP, completed_at = CURRENT_TIMESTAMP,
                lease_token = NULL
            WHERE id = :artifact_id AND status = 'generating' AND lease_token = :lease_token
            """
        ),
        {"artifact_id": artifact_id, "payload": json.dumps(payload, ensure_ascii=False), "lease_token": lease_token},
    )
    if result.rowcount != 1:
        db.session.rollback()
        raise RuntimeError("AI generation lease was lost before publishing the result")
    db.session.commit()


def mark_generation_failed(artifact_id: int, error_message: str, lease_token: str | None = None) -> None:
    from sqlalchemy import text
    from app import db
    if not lease_token:
        raise ValueError("lease_token is required to release an AI generation")
    result = db.session.execute(
        text(
            """
            UPDATE ai_generation_artifact
            SET status = 'failed', error_message = :error_message,
                updated_at = CURRENT_TIMESTAMP, completed_at = CURRENT_TIMESTAMP,
                lease_token = NULL
            WHERE id = :artifact_id AND status = 'generating' AND lease_token = :lease_token
            """
        ),
        {"artifact_id": artifact_id, "error_message": error_message[:4000], "lease_token": lease_token},
    )
    if result.rowcount != 1:
        db.session.rollback()
        raise RuntimeError("AI generation lease was lost before releasing the result")
    db.session.commit()
