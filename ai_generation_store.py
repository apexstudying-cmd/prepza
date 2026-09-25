"""Persistence primitives for fingerprinted AI artifact generation."""

from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any


GENERATION_LEASE_SECONDS = 15 * 60

_SCHEMA_READY = False
_SCHEMA_LOCK = Lock()


def _ensure_schema():
    """Compatibility bootstrap for environments where SQL migrations are not auto-run."""
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    from sqlalchemy import text
    from app import db
    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS ai_generation_artifact (
                id BIGSERIAL PRIMARY KEY,
                fingerprint VARCHAR(128) NOT NULL UNIQUE,
                content_hash VARCHAR(128) NOT NULL,
                feature VARCHAR(40) NOT NULL,
                parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
                prompt_version VARCHAR(80) NOT NULL,
                schema_version VARCHAR(80) NOT NULL,
                scope VARCHAR(20) NOT NULL DEFAULT 'shared',
                owner_user_id INTEGER NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'generating',
                payload JSONB NULL,
                error_message VARCHAR(4000) NULL,
                lease_token VARCHAR(128) NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP NULL
            )
        """))
        db.session.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_ai_generation_artifact_content_feature
            ON ai_generation_artifact (content_hash, feature)
        """))
        db.session.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_ai_generation_artifact_status_updated
            ON ai_generation_artifact (status, updated_at)
        """))
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS ai_generation_variant_family (
                base_fingerprint VARCHAR(64) PRIMARY KEY,
                feature VARCHAR(40) NOT NULL,
                base_parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
                next_variant SMALLINT NOT NULL DEFAULT 1,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS ai_generation_variant_access (
                user_id INTEGER NOT NULL,
                base_fingerprint VARCHAR(64) NOT NULL,
                variant SMALLINT NOT NULL,
                artifact_id BIGINT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'reserved',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, base_fingerprint, variant)
            )
        """))
        db.session.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_ai_generation_variant_access_family
            ON ai_generation_variant_access (base_fingerprint, variant, status)
        """))
        db.session.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_ai_generation_variant_access_artifact
            ON ai_generation_variant_access (artifact_id)
        """))
        db.session.commit()
        _SCHEMA_READY = True


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
    _ensure_schema()
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
            SELECT id, status, payload, scope, owner_user_id, updated_at, lease_token,
                   content_hash, feature, parameters, prompt_version, schema_version
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

    # A fingerprint collision or caller bug must never silently reuse an
    # artifact generated from a different request. The fingerprint is the
    # primary key, but these persisted inputs are the defense-in-depth check.
    persisted_parameters = existing["parameters"] or {}
    if isinstance(persisted_parameters, str):
        persisted_parameters = json.loads(persisted_parameters)
    if (
        existing["content_hash"] != content_hash
        or existing["feature"] != feature
        or persisted_parameters != (parameters or {})
        or existing["prompt_version"] != prompt_version
        or existing["schema_version"] != schema_version
    ):
        raise RuntimeError("AI artifact fingerprint/input mismatch")

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
