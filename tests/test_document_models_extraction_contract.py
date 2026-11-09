"""Guard document, generation, and tutor model extraction."""

from pathlib import Path

from extensions import db


ROOT = Path(__file__).resolve().parents[1]


def test_document_models_keep_shared_metadata_columns_and_constraints():
    import document_models

    expected = {
        "document_content",
        "document_page_text",
        "document",
        "document_reading_progress",
        "generated_material",
        "ai_job",
        "tutor_conversation",
        "tutor_message",
    }
    assert expected <= set(db.metadata.tables)
    assert document_models.DocumentContent.__tablename__ == "document_content"
    assert document_models.DocumentPageText.__tablename__ == "document_page_text"
    assert document_models.Document.__tablename__ == "document"
    assert document_models.DocumentReadingProgress.__tablename__ == "document_reading_progress"
    assert document_models.GeneratedMaterial.__tablename__ == "generated_material"
    assert document_models.AiJob.__tablename__ == "ai_job"
    assert document_models.TutorConversation.__tablename__ == "tutor_conversation"
    assert document_models.TutorMessage.__tablename__ == "tutor_message"

    generated_columns = set(db.metadata.tables["generated_material"].columns.keys())
    assert {
        "generation_fingerprint", "generation_parameters", "generation_version",
        "scope", "owner_user_id",
    } <= generated_columns
    page_columns = set(db.metadata.tables["document_page_text"].columns.keys())
    assert {"page_number", "page_text", "content_hash", "source_version", "extractor_version"} <= page_columns
    tutor_columns = set(db.metadata.tables["tutor_message"].columns.keys())
    assert {"conversation_id", "role", "content", "created_at"} <= tutor_columns

    constraints = {
        table: {item.name for item in db.metadata.tables[table].constraints}
        for table in ("document_page_text", "document_reading_progress", "tutor_conversation")
    }
    assert "uq_document_page_text_content_page" in constraints["document_page_text"]
    assert "uq_document_reading_progress_user_document" in constraints["document_reading_progress"]
    assert "uq_tutor_conv_user_doc" in constraints["tutor_conversation"]


def test_app_reexports_document_models_for_legacy_imports():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    expected_import = (
        "from document_models import (\n"
        "    DocumentContent, DocumentPageText, Document, DocumentReadingProgress,\n"
        "    GeneratedMaterial, AiJob, TutorConversation, TutorMessage,\n"
        ")"
    )
    assert expected_import in source
    for name in (
        "DocumentContent", "DocumentPageText", "Document", "DocumentReadingProgress",
        "GeneratedMaterial", "AiJob", "TutorConversation", "TutorMessage",
    ):
        assert f"class {name}(db.Model):" not in source
