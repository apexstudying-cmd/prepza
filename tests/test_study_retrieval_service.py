"""Access-control and citation-quality contracts for persisted page retrieval."""
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from study_retrieval_service import load_authorized_pages, retrieve_authorized_pages


@pytest.fixture
def retrieval_db():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE "user" (
                id INTEGER PRIMARY KEY, university_id INTEGER, program_id INTEGER,
                year INTEGER, semester INTEGER
            )
        """))
        conn.execute(text("""
            CREATE TABLE document_content (
                id INTEGER PRIMARY KEY, status TEXT NOT NULL, content_hash TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE document (
                id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL,
                document_content_id INTEGER NOT NULL, status TEXT NOT NULL,
                is_removed BOOLEAN NOT NULL DEFAULT 0
            )
        """))
        conn.execute(text("""
            CREATE TABLE library_publication (
                id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL, status TEXT NOT NULL,
                university_id INTEGER, program_id INTEGER, year INTEGER, semester INTEGER
            )
        """))
        conn.execute(text("""
            CREATE TABLE document_page_text (
                id INTEGER PRIMARY KEY, document_content_id INTEGER NOT NULL,
                page_number INTEGER NOT NULL, page_text TEXT NOT NULL,
                source_version TEXT NOT NULL, content_hash TEXT NOT NULL
            )
        """))
        conn.execute(text("INSERT INTO \"user\" VALUES (100, 1, 10, 2, 1), (200, 2, 20, 2, 1), (300, 3, 30, 2, 1)"))
        conn.execute(text("INSERT INTO document_content VALUES (1, 'ready', 'hash-one'), (2, 'ready', 'hash-two'), (3, 'processing', 'hash-three')"))
        conn.execute(text("INSERT INTO document VALUES (10, 100, 1, 'ready', 0), (20, 200, 2, 'ready', 0), (30, 100, 3, 'processing', 0), (40, 100, 1, 'ready', 1)"))
        conn.execute(text("INSERT INTO library_publication VALUES (1, 20, 'pending', 1, 10, 2, 1)"))
        conn.execute(text("INSERT INTO document_page_text VALUES (1, 1, 1, 'Calculus derivatives measure rates of change.', 'v1', 'hash-one'), (2, 2, 1, 'Private exam answer key and confidential grades.', 'v2', 'hash-two'), (3, 3, 1, 'Unready text must not be returned.', 'v3', 'hash-three')"))
    try:
        yield engine
    finally:
        engine.dispose()


def test_retrieval_loads_only_documents_authorized_for_requester(retrieval_db):
    with retrieval_db.connect() as conn:
        pages = retrieve_authorized_pages(conn, user_id=100, query="derivatives rates of change")

    assert pages
    assert {page.document_id for page in pages} == {10}
    assert pages[0].citation == {
        "document_id": 10,
        "document_version": "v1",
        "page_number": 1,
    }
    assert all("confidential" not in page.text for page in pages)
    assert all("Unready" not in page.text for page in pages)


def test_approved_library_publication_can_be_retrieved_by_non_owner(retrieval_db):
    with retrieval_db.begin() as conn:
        conn.execute(text("UPDATE library_publication SET status='approved' WHERE document_id=20"))

    with retrieval_db.connect() as conn:
        pages = retrieve_authorized_pages(conn, user_id=100, query="exam answer key")

    assert any(page.document_id == 20 for page in pages)

    # The same approved publication must not leak to a student in a different
    # university/program cohort, even when the content hash is identical.
    with retrieval_db.connect() as conn:
        wrong_cohort = retrieve_authorized_pages(
            conn, user_id=300, query="exam answer key", document_id=20,
        )
    assert wrong_cohort == []


def test_removed_owner_document_is_not_retrievable(retrieval_db):
    with retrieval_db.connect() as conn:
        pages = retrieve_authorized_pages(conn, user_id=100, query="derivatives rates of change")
    assert all(page.document_id != 40 for page in pages)


def test_citation_evaluation_dataset_meets_retrieval_quality_thresholds():
    dataset_path = Path(__file__).parent / "fixtures" / "study_retrieval_eval.json"
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    assert len(dataset["cases"]) >= 8

    from study_retrieval import StudyChunk, hybrid_retrieve

    corpus = [
        StudyChunk(
            document_id=page["document_id"], document_version=page["document_version"],
            page_number=page["page_number"], chunk_index=0, text=page["text"],
            start_char=0, end_char=len(page["text"]),
        )
        for page in dataset["corpus"]
    ]
    expected_total = 0
    retrieved_expected = 0
    reciprocal_ranks = []
    precisions = []
    for item in dataset["cases"]:
        expected = {
            (source["document_id"], source["page_number"])
            for source in item["expected_sources"]
        }
        expected_total += len(expected)
        results = hybrid_retrieve(
            item["query"], corpus,
            allowed_document_ids={page.document_id for page in corpus},
            top_k=5,
        )
        ranked_sources = [
            (result.chunk.document_id, result.chunk.page_number)
            for result in results
        ]
        found = expected.intersection(ranked_sources)
        retrieved_expected += len(found)
        precisions.append(len(found) / max(1, len(ranked_sources)))
        first_relevant_rank = next(
            (rank for rank, source in enumerate(ranked_sources, start=1) if source in expected),
            None,
        )
        reciprocal_ranks.append(1 / first_relevant_rank if first_relevant_rank else 0.0)

        for result in results:
            assert result.citation == {
                "document_id": result.chunk.document_id,
                "document_version": result.chunk.document_version,
                "page_number": result.chunk.page_number,
            }

    recall_at_five = retrieved_expected / max(1, expected_total)
    mean_reciprocal_rank_at_five = sum(reciprocal_ranks) / len(reciprocal_ranks)
    mean_precision_at_five = sum(precisions) / len(precisions)
    assert recall_at_five >= 0.8, f"citation Recall@5 was {recall_at_five:.0%}"
    assert mean_reciprocal_rank_at_five >= 0.3, (
        f"citation MRR@5 was {mean_reciprocal_rank_at_five:.3f}"
    )
    assert mean_precision_at_five >= 0.15, (
        f"citation Precision@5 was {mean_precision_at_five:.0%}"
    )

def test_page_source_version_changes_when_extracted_page_changes():
    from study_retrieval_service import make_source_version

    original = make_source_version("hash", ["page one", "page two"], extractor_version="pdf-page-text-v1")
    same = make_source_version("hash", ["page one", "page two"], extractor_version="pdf-page-text-v1")
    changed = make_source_version("hash", ["page one corrected", "page two"], extractor_version="pdf-page-text-v1")
    extractor_upgrade = make_source_version("hash", ["page one", "page two"], extractor_version="pdf-page-text-v2")

    assert original == same
    assert original != changed
    assert original != extractor_upgrade


def test_unauthorized_document_does_not_trigger_embedding_callbacks(retrieval_db):
    def must_not_run(_value):
        raise AssertionError("unauthorized text must not reach embedding callbacks")

    with retrieval_db.connect() as conn:
        pages = retrieve_authorized_pages(
            conn, user_id=999, query="confidential grades",
            embed_query=must_not_run, embed_text=must_not_run,
        )

    assert pages == []


def test_document_scope_cannot_bypass_ownership_or_publication(retrieval_db):
    with retrieval_db.connect() as conn:
        private_pages = retrieve_authorized_pages(
            conn, user_id=100, query="confidential grades", document_id=20,
        )
    assert private_pages == []

    with retrieval_db.begin() as conn:
        conn.execute(text("UPDATE library_publication SET status='approved' WHERE document_id=20"))
    with retrieval_db.connect() as conn:
        published_pages = retrieve_authorized_pages(
            conn, user_id=100, query="confidential grades", document_id=20,
        )
    assert published_pages
    assert {page.document_id for page in published_pages} == {20}


def test_authorized_page_loading_has_a_hard_row_cap(retrieval_db):
    with retrieval_db.begin() as conn:
        conn.execute(text("INSERT INTO document VALUES (11, 100, 1, 'ready', 0)"))

    with retrieval_db.connect() as conn:
        pages = load_authorized_pages(conn, user_id=100, max_pages=1)

    assert len(pages) == 1
    assert pages[0].document_id == 11



def test_page_index_match_rejects_partial_or_stale_rows():
    from types import SimpleNamespace
    from study_retrieval_service import page_index_matches

    rows = [
        SimpleNamespace(
            page_number=1, page_text="first page", content_hash="hash",
            source_version="v2", extractor_version="extractor-2",
        ),
        SimpleNamespace(
            page_number=2, page_text="second page", content_hash="hash",
            source_version="v2", extractor_version="extractor-2",
        ),
    ]
    expected = {
        "content_hash": "hash",
        "source_version": "v2",
        "extractor_version": "extractor-2",
    }

    assert page_index_matches(rows, ["first page", "second page"], **expected)
    assert not page_index_matches(rows[:1], ["first page", "second page"], **expected)
    assert not page_index_matches(rows, ["first page", "corrected page"], **expected)

    rows[1].source_version = "old-version"
    assert not page_index_matches(rows, ["first page", "second page"], **expected)
