"""Authorization-first retrieval over persisted, page-preserving study text.

The query joins through the canonical Document row on every retrieval. Shared
content hashes do not grant access: the requester must own a non-removed,
ready document or the source document must have an approved LibraryPublication.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Callable, Sequence

from sqlalchemy import text

from study_retrieval import StudyChunk, chunk_pages, hybrid_retrieve

MAX_AUTHORIZED_PAGE_ROWS = 250
MAX_RETRIEVAL_CHUNKS = 500
MAX_PAGE_TEXT_CHARS = 20_000


@dataclass(frozen=True)
class AuthorizedPage:
    document_id: int
    document_content_id: int
    page_number: int
    text: str
    source_version: str


@dataclass(frozen=True)
class RetrievedPage:
    document_id: int
    document_content_id: int
    page_number: int
    text: str
    source_version: str
    score: float
    lexical_score: float
    semantic_score: float | None

    @property
    def citation(self) -> dict:
        return {
            "document_id": self.document_id,
            "document_version": self.source_version,
            "page_number": self.page_number,
        }


_AUTHORIZED_PAGE_SQL = text("""
    SELECT DISTINCT
        d.id AS document_id,
        c.id AS document_content_id,
        p.page_number AS page_number,
        p.page_text AS page_text,
        p.source_version AS source_version
    FROM document_page_text AS p
    JOIN document_content AS c ON c.id = p.document_content_id
    JOIN document AS d ON d.document_content_id = c.id
    LEFT JOIN "user" AS viewer ON viewer.id = :user_id
    LEFT JOIN library_publication AS lp
      ON lp.document_id = d.id
     AND lp.status = 'approved'
     AND lp.university_id = viewer.university_id
     AND lp.program_id = viewer.program_id
     AND lp.year = viewer.year
     AND lp.semester = viewer.semester
    WHERE d.status = 'ready'
      AND d.is_removed = FALSE
      AND c.status = 'ready'
      AND (d.user_id = :user_id OR lp.id IS NOT NULL)
      AND (:document_id IS NULL OR d.id = :document_id)
      AND p.page_text <> ''
    ORDER BY d.id DESC, p.page_number ASC
    LIMIT :max_pages
""")


def load_authorized_pages(
    connection, *, user_id: int, document_id: int | None = None,
    max_pages: int = MAX_AUTHORIZED_PAGE_ROWS,
) -> list[AuthorizedPage]:
    """Load page text only after the database applies the caller's access scope."""
    if user_id is None or max_pages <= 0:
        return []
    rows = connection.execute(_AUTHORIZED_PAGE_SQL, {
        "user_id": user_id, "document_id": document_id, "max_pages": max_pages,
    }).mappings()
    return [
        AuthorizedPage(
            document_id=int(row["document_id"]),
            document_content_id=int(row["document_content_id"]),
            page_number=int(row["page_number"]),
            text=str(row["page_text"]),
            source_version=str(row["source_version"]),
        )
        for row in rows
    ]


def retrieve_authorized_pages(
    connection,
    *,
    user_id: int,
    query: str,
    top_k: int = 5,
    document_id: int | None = None,
    authorized_pages: Sequence[AuthorizedPage] | None = None,
    embed_query: Callable[[str], Sequence[float]] | None = None,
    embed_text: Callable[[str], Sequence[float]] | None = None,
) -> list[RetrievedPage]:
    """Retrieve relevant pages from the authorized corpus with stable citations.

    Embedding callbacks are called only after the authorization-filtered SQL
    query has returned. The caller must pass the authenticated session user ID,
    never an untrusted user ID from a request body.
    """
    pages = (
        list(authorized_pages) if authorized_pages is not None
        else load_authorized_pages(connection, user_id=user_id, document_id=document_id)
    )
    chunks: list[StudyChunk] = []
    by_identity: dict[tuple[int, int, int], AuthorizedPage] = {}
    for page in pages:
        page_chunks = chunk_pages(
            document_id=page.document_id,
            document_version=page.source_version,
            pages=[""] * (page.page_number - 1) + [page.text[:MAX_PAGE_TEXT_CHARS]],
            max_chars=1200,
            overlap_chars=160,
        )
        # The page list is intentionally indexed 1-based by chunk_pages. Only
        # chunks belonging to this page are retained for this source document.
        for chunk in page_chunks:
            if chunk.page_number != page.page_number:
                continue
            chunks.append(chunk)
            by_identity[(page.document_id, page.page_number, chunk.chunk_index)] = page
            if len(chunks) >= MAX_RETRIEVAL_CHUNKS:
                break
        if len(chunks) >= MAX_RETRIEVAL_CHUNKS:
            break

    results = hybrid_retrieve(
        query,
        chunks,
        allowed_document_ids={page.document_id for page in pages},
        embed_query=embed_query,
        embed_text=embed_text,
        top_k=min(max(top_k * 5, top_k), 50),
    )
    retrieved: list[RetrievedPage] = []
    seen: set[tuple[int, int]] = set()
    for result in results:
        identity = (int(result.chunk.document_id), result.chunk.page_number)
        if identity in seen:
            continue
        seen.add(identity)
        source = by_identity[(identity[0], identity[1], result.chunk.chunk_index)]
        retrieved.append(RetrievedPage(
            document_id=source.document_id,
            document_content_id=source.document_content_id,
            page_number=source.page_number,
            text=result.chunk.text,
            source_version=source.source_version,
            score=result.score,
            lexical_score=result.lexical_score,
            semantic_score=result.semantic_score,
        ))
        if len(retrieved) >= top_k:
            break
    return retrieved


def make_source_version(content_hash: str, page_texts: Sequence[str], *, extractor_version: str) -> str:
    """Content-address the extracted page set and extraction contract."""
    digest = hashlib.sha256()
    digest.update((content_hash or "").encode("utf-8"))
    digest.update(b"\0")
    digest.update(extractor_version.encode("utf-8"))
    for page_number, page_text in enumerate(page_texts, start=1):
        digest.update(b"\0")
        digest.update(str(page_number).encode("ascii"))
        digest.update(b"\0")
        digest.update(page_text.encode("utf-8"))
    return digest.hexdigest()
