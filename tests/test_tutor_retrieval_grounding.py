from pathlib import Path

from ai_service import _build_tutor_system_prompt

ROOT = Path(__file__).resolve().parents[1]


def test_retrieval_prompt_requires_page_citations_and_insufficient_evidence_behavior():
    prompt = _build_tutor_system_prompt(
        unit_context="their coursework",
        document_text="",
        page_count=12,
        retrieval_mode=True,
        include_document_text=False,
    )

    assert "You are Morio, Prepza's AI tutor." in prompt
    assert "relevant retrieved excerpts" in prompt
    assert "Ground every answer in the document text below" in prompt
    assert "cite source-based claims using [p. N]" in prompt
    assert "retrieved pages do not establish it rather than guessing" in prompt
    assert "DOCUMENT TEXT:" not in prompt


def test_legacy_prompt_keeps_full_document_fallback_for_unindexed_documents():
    prompt = _build_tutor_system_prompt(
        unit_context="their coursework",
        document_text="legacy extracted text",
        page_count=2,
    )

    assert "reproduced in full below" in prompt
    assert "DOCUMENT TEXT:\nlegacy extracted text" in prompt
    assert "cite source-based claims using [p. N]" not in prompt


def test_main_tutor_passes_document_scope_into_authorized_retrieval():
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    ai_source = (ROOT / "ai_service.py").read_text(encoding="utf-8")
    route_start = app_source.index('def send_tutor_message(document_id):')
    route_end = app_source.index('@app.route("/documents/<int:document_id>/tutor", methods=["DELETE"])', route_start)
    route = app_source[route_start:route_end]
    tutor_start = ai_source.index("def generate_tutor_reply(")
    tutor_end = ai_source.index("def ", tutor_start + 5)
    tutor = ai_source[tutor_start:tutor_end]

    assert "document_id=document_id" in route
    assert "user_id=triggering_user_id, document_id=document_id" in tutor
    assert "authorized_pages=authorized_pages" in tutor
    assert "Secure document retrieval is temporarily unavailable" in tutor
