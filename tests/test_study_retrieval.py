"""Provider-free contract tests for page-cited hybrid study retrieval."""

from study_retrieval import StudyChunk, chunk_pages, hybrid_retrieve


def test_chunk_pages_preserves_document_version_and_page_citations():
    pages = [
        "Algebra basics. Linear equations solve for an unknown. " * 8,
        "Probability uses sample spaces and event probabilities. " * 8,
    ]
    chunks = chunk_pages(
        document_id=12,
        document_version="sha256:version-a",
        pages=pages,
        max_chars=180,
        overlap_chars=30,
    )

    assert chunks
    assert {chunk.page_number for chunk in chunks} == {1, 2}
    assert all(chunk.document_id == 12 for chunk in chunks)
    assert all(chunk.document_version == "sha256:version-a" for chunk in chunks)
    assert all(chunk.text.strip() for chunk in chunks)
    assert all(len(chunk.text) <= 180 for chunk in chunks)
    assert all(chunk.start_char < chunk.end_char for chunk in chunks)
    page_one = [chunk for chunk in chunks if chunk.page_number == 1]
    assert len(page_one) > 1
    assert page_one[0].text[-30:].strip() in page_one[1].text


def test_hybrid_retrieval_returns_citations_and_excludes_unauthorized_docs_before_embedding():
    chunks = [
        StudyChunk(1, "v1", 2, 0, "Bayes theorem updates probability using evidence.", 0, 48),
        StudyChunk(2, "v9", 7, 0, "Private exam answers and confidential marks.", 0, 44),
        StudyChunk(1, "v1", 4, 0, "A derivative measures instantaneous rate of change.", 0, 50),
    ]
    embedded_texts = []

    def embed_text(text):
        embedded_texts.append(text)
        return [1.0, 0.0] if "Bayes" in text else [0.0, 1.0]

    results = hybrid_retrieve(
        "Bayes probability evidence",
        chunks,
        allowed_document_ids={1},
        embed_query=lambda _query: [1.0, 0.0],
        embed_text=embed_text,
        top_k=2,
    )

    assert results
    assert results[0].chunk.page_number == 2
    assert results[0].chunk.document_id == 1
    assert all(result.chunk.document_id == 1 for result in results)
    assert all("confidential" not in text for text in embedded_texts)
    assert results[0].citation == {"document_id": 1, "document_version": "v1", "page_number": 2}


def test_retrieval_is_lexical_only_without_embedding_adapter():
    chunks = [
        StudyChunk(4, "v3", 1, 0, "A matrix stores values in rows and columns.", 0, 42),
        StudyChunk(4, "v3", 3, 0, "Conditional probability depends on prior information.", 0, 51),
    ]

    results = hybrid_retrieve(
        "conditional probability",
        chunks,
        allowed_document_ids={4},
        top_k=1,
    )

    assert len(results) == 1
    assert results[0].chunk.page_number == 3
    assert results[0].semantic_score is None
    assert results[0].lexical_score > 0


def test_empty_authorized_scope_never_calls_embedding_functions():
    chunks = [StudyChunk(2, "v1", 1, 0, "private note", 0, 12)]

    def should_not_run(_value):
        raise AssertionError("embeddings must not run for an empty authorized scope")

    assert hybrid_retrieve(
        "private note",
        chunks,
        allowed_document_ids=set(),
        embed_query=should_not_run,
        embed_text=should_not_run,
    ) == []


def test_punctuation_only_query_returns_no_candidates():
    chunks = [StudyChunk(1, "v1", 1, 0, "Some course text.", 0, 17)]
    assert hybrid_retrieve("?!", chunks, allowed_document_ids={1}) == []


def test_lexical_only_retrieval_rejects_zero_lexical_weight():
    chunks = [StudyChunk(1, "v1", 1, 0, "Some course text.", 0, 17)]
    import pytest
    with pytest.raises(ValueError, match="lexical_weight"):
        hybrid_retrieve(
            "course text", chunks, allowed_document_ids={1},
            lexical_weight=0, semantic_weight=1,
        )
