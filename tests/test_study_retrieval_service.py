"""Access-control and citation-quality contracts for persisted page retrieval."""
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from study_retrieval_service import retrieve_authorized_pages


@pytest.fixture
def retrieval_db():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
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
                id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL, status TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE document_page_text (
                id INTEGER PRIMARY KEY, document_content_id INTEGER NOT NULL,
                page_number INTEGER NOT NULL, page_text TEXT NOT NULL,
                source_version TEXT NOT NULL, content_hash TEXT NOT NULL
            )
        """))
        conn.execute(text("INSERT INTO document_content VALUES (1, 'ready', 'hash-one'), (2, 'ready', 'hash-two'), (3, 'processing', 'hash-three')"))
        conn.execute(text("INSERT INTO document VALUES (10, 100, 1, 'ready', 0), (20, 200, 2, 'ready', 0), (30, 100, 3, 'processing', 0), (40, 100, 1, 'ready', 1)"))
        conn.execute(text("INSERT INTO library_publication VALUES (1, 20, 'pending')"))
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
    assert all("confidential" not in page.text for page in pages)
    assert all("Unready" not in page.text for page in pages)


def test_approved_library_publication_can_be_retrieved_by_non_owner(retrieval_db):
    with retrieval_db.begin() as conn:
        conn.execute(text("UPDATE library_publication SET status='approved' WHERE document_id=20"))

    with retrieval_db.connect() as conn:
        pages = retrieve_authorized_pages(conn, user_id=100, query="exam answer key")

    assert any(page.document_id == 20 for page in pages)


def test_removed_owner_document_is_not_retrievable(retrieval_db):
    with retrieval_db.connect() as conn:
        pages = retrieve_authorized_pages(conn, user_id=100, query="derivatives rates of change")
    assert all(page.document_id != 40 for page in pages)


def test_citation_evaluation_dataset_meets_recall_at_five_threshold():
    dataset_path = Path(__file__).parent / "fixtures" / "study_retrieval_eval.json"
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    assert len(dataset) >= 8

    hits = 0
    for item in dataset:
        expected = {(source["document_id"], source["page_number"]) for source in item["expected_sources"]}
        retrieved = {(source["document_id"], source["page_number"]) for source in item["retrieved_sources"]}
        hits += bool(expected & retrieved)

    recall_at_five = hits / len(dataset)
    assert recall_at_five >= 0.8, f"citation Recall@5 was {recall_at_five:.0%}"
