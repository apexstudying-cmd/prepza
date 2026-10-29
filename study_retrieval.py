"""Provider-neutral, page-cited retrieval primitives for study-note RAG.

This module is deliberately not wired into a user-facing tutor yet. Callers
must obtain chunks only after server-side authorization; allowed_document_ids
must come from trusted backend checks, never from client-supplied IDs. Embedding
functions are injected so tests and local development never make billable calls.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence


_TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)


@dataclass(frozen=True)
class StudyChunk:
    document_id: int | str
    document_version: str
    page_number: int
    chunk_index: int
    text: str
    start_char: int
    end_char: int


@dataclass(frozen=True)
class RetrievalResult:
    chunk: StudyChunk
    score: float
    lexical_score: float
    semantic_score: float | None

    @property
    def citation(self) -> dict:
        """Stable source identity suitable for a citation envelope."""
        return {
            "document_id": self.chunk.document_id,
            "document_version": self.chunk.document_version,
            "page_number": self.chunk.page_number,
        }


def chunk_pages(
    *,
    document_id: int | str,
    document_version: str,
    pages: Sequence[str],
    max_chars: int = 1200,
    overlap_chars: int = 160,
) -> list[StudyChunk]:
    """Split each page independently, retaining stable page and offset metadata."""
    if not document_version or not document_version.strip():
        raise ValueError("document_version is required")
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be between zero and max_chars - 1")

    chunks: list[StudyChunk] = []
    for page_index, page in enumerate(pages, start=1):
        if not isinstance(page, str):
            raise TypeError("every page must be text")
        if not page.strip():
            continue
        start = 0
        chunk_index = 0
        while start < len(page):
            end = min(start + max_chars, len(page))
            left, right = start, end
            while left < right and page[left].isspace():
                left += 1
            while right > left and page[right - 1].isspace():
                right -= 1
            if left < right:
                chunks.append(StudyChunk(
                    document_id=document_id,
                    document_version=document_version,
                    page_number=page_index,
                    chunk_index=chunk_index,
                    text=page[left:right],
                    start_char=left,
                    end_char=right,
                ))
                chunk_index += 1
            if end >= len(page):
                break
            start = end - overlap_chars
    return chunks


def _tokens(text: str) -> set[str]:
    return {token.casefold() for token in _TOKEN_RE.findall(text)}


def _lexical_score(query_tokens: set[str], text: str) -> float:
    if not query_tokens:
        return 0.0
    return len(query_tokens.intersection(_tokens(text))) / len(query_tokens)


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or not right:
        return 0.0
    if len(left) != len(right):
        raise ValueError("embedding vectors must have the same dimensions")
    left_values = [float(value) for value in left]
    right_values = [float(value) for value in right]
    if not all(math.isfinite(value) for value in left_values + right_values):
        raise ValueError("embedding vectors must contain finite numbers")
    left_norm = math.sqrt(sum(value * value for value in left_values))
    right_norm = math.sqrt(sum(value * value for value in right_values))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    cosine = sum(a * b for a, b in zip(left_values, right_values)) / (left_norm * right_norm)
    # Map cosine [-1, 1] into a stable score range [0, 1].
    return max(0.0, min(1.0, (cosine + 1.0) / 2.0))


def hybrid_retrieve(
    query: str,
    chunks: Iterable[StudyChunk],
    *,
    allowed_document_ids: set[int | str],
    embed_query: Callable[[str], Sequence[float]] | None = None,
    embed_text: Callable[[str], Sequence[float]] | None = None,
    top_k: int = 5,
    lexical_weight: float = 0.55,
    semantic_weight: float = 0.45,
) -> list[RetrievalResult]:
    """Rank authorized chunks with lexical overlap plus optional injected embeddings.

    The authorization filter is applied before embedding callbacks run. The
    caller still owns the security-critical step of deriving the allowed ID set
    from authenticated user/course/share checks and loading the correct chunks.
    """
    if not isinstance(query, str) or not query.strip():
        return []
    query_tokens = _tokens(query)
    if not query_tokens:
        return []
    if top_k <= 0:
        return []
    if (embed_query is None) != (embed_text is None):
        raise ValueError("embed_query and embed_text must be provided together")
    if lexical_weight < 0 or semantic_weight < 0 or lexical_weight + semantic_weight <= 0:
        raise ValueError("retrieval weights must be non-negative with a positive total")
    if embed_query is None and lexical_weight <= 0:
        raise ValueError("lexical_weight must be positive without an embedding adapter")
    authorized = [
        chunk for chunk in chunks
        if chunk.document_id in allowed_document_ids and chunk.text.strip()
    ]
    if not authorized:
        return []

    lexical_scores = [_lexical_score(query_tokens, chunk.text) for chunk in authorized]
    semantic_scores: list[float | None]
    if embed_query is None:
        semantic_scores = [None] * len(authorized)
        # A lexical-only result is the fraction of query terms found; do not
        # rescale it by the hybrid weight because no semantic score exists.
        scores = list(lexical_scores)
    else:
        query_vector = embed_query(query)
        vectors = [embed_text(chunk.text) for chunk in authorized]
        semantic_scores = [_cosine_similarity(query_vector, vector) for vector in vectors]
        denominator = lexical_weight + semantic_weight
        scores = [
            (lexical_weight * lexical + semantic_weight * semantic) / denominator
            for lexical, semantic in zip(lexical_scores, semantic_scores)
        ]

    ranked = [
        RetrievalResult(
            chunk=chunk,
            score=float(score),
            lexical_score=float(lexical),
            semantic_score=None if semantic is None else float(semantic),
        )
        for chunk, score, lexical, semantic in zip(
            authorized, scores, lexical_scores, semantic_scores
        )
    ]
    ranked.sort(
        key=lambda result: (
            -result.score,
            -result.lexical_score,
            result.chunk.page_number,
            result.chunk.chunk_index,
        )
    )
    return ranked[:top_k]
