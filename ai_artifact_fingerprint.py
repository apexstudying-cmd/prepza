"""Deterministic identity for reusable AI-generated learning artifacts."""

from __future__ import annotations

import hashlib
import json
from typing import Any


# Bump whenever the reusable-generation contract changes in a way that must
# invalidate previously generated artifacts.
GENERATION_VERSION = "v2"


def build_generation_fingerprint(
    *,
    content_hash: str,
    material_type: str,
    parameters: dict[str, Any] | None = None,
    prompt_version: str = GENERATION_VERSION,
    schema_version: str = GENERATION_VERSION,
    scope: str = "shared",
    owner_user_id: int | None = None,
) -> str:
    """Return a stable SHA-256 identity for one generation variant."""
    normalized_scope = str(scope).strip().lower()
    if normalized_scope not in {"shared", "private"}:
        raise ValueError("scope must be 'shared' or 'private'")
    if normalized_scope == "private" and owner_user_id is None:
        raise ValueError("private artifacts require owner_user_id")
    if normalized_scope == "shared" and owner_user_id is not None:
        raise ValueError("shared artifacts must not include owner_user_id")

    canonical = {
        "content_hash": str(content_hash),
        "material_type": str(material_type),
        "parameters": parameters or {},
        "prompt_version": str(prompt_version),
        "schema_version": str(schema_version),
        "scope": normalized_scope,
        "owner_user_id": int(owner_user_id) if owner_user_id is not None else None,
    }
    encoded = json.dumps(
        canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
