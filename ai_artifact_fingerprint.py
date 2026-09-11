"""Deterministic identity for reusable AI-generated learning artifacts."""

from __future__ import annotations

import hashlib
import json
from typing import Any


GENERATION_VERSION = "v1"


def build_generation_fingerprint(
    *,
    content_hash: str,
    material_type: str,
    parameters: dict[str, Any] | None = None,
    prompt_version: str = GENERATION_VERSION,
    schema_version: str = GENERATION_VERSION,
) -> str:
    """Return a stable SHA-256 identity for one generation variant.

    The source *content hash* is intentionally used instead of a Document id,
    so identical shared documents can reuse the same artifact. Parameters,
    prompt version, and output schema version are part of the identity so a
    changed request cannot accidentally receive an incompatible artifact.
    """

    canonical = {
        "content_hash": str(content_hash),
        "material_type": str(material_type),
        "parameters": parameters or {},
        "prompt_version": str(prompt_version),
        "schema_version": str(schema_version),
    }
    encoded = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
