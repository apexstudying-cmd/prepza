"""Runtime regression tests for document OCR routing."""

from unittest.mock import patch

import document_pipeline


class _FakePage:
    def get_text(self):
        return ""


class _FakeDoc:
    def __init__(self, count):
        self.pages = [_FakePage() for _ in range(count)]

    def __len__(self):
        return len(self.pages)

    def __getitem__(self, index):
        return self.pages[index]

    def close(self):
        pass


def test_scanned_pdf_uses_sync_ocr_when_batch_adapter_is_missing():
    doc = _FakeDoc(3)
    with patch.object(document_pipeline.fitz, "open", return_value=doc), \
         patch.object(document_pipeline, "_get_ocr_batch_threshold", return_value=2), \
         patch.object(document_pipeline, "_render_page_png", side_effect=lambda page: b"png"), \
         patch.object(document_pipeline, "_transcribe_page_image", side_effect=["one", "two", "three"]) as transcribe:
        text, page_count = document_pipeline._extract_pdf_text(b"pdf", None)

    assert page_count == 3
    assert text == "one\n\ntwo\n\nthree"
    assert transcribe.call_count == 3



def test_pdf_extraction_preserves_individual_page_text():
    doc = _FakeDoc(3)
    with patch.object(document_pipeline.fitz, "open", return_value=doc), \
         patch.object(document_pipeline, "_get_ocr_batch_threshold", return_value=2), \
         patch.object(document_pipeline, "_render_page_png", side_effect=lambda page: b"png"), \
         patch.object(document_pipeline, "_transcribe_page_image", side_effect=["page one", "page two", "page three"]):
        pages, page_count = document_pipeline._extract_pdf_pages(b"pdf", None)

    assert page_count == 3
    assert pages == ["page one", "page two", "page three"]


def test_reextraction_invalidates_only_when_source_text_changes():
    changed_pages = document_pipeline.extracted_text_changed(
        ["page one", "page two"], "\n\n".join(["page one", "page two"]), ["page one corrected", "page two"]
    )
    unchanged_pages = document_pipeline.extracted_text_changed(
        ["page one", "page two"], "\n\n".join(["page one", "page two"]), ["page one", "page two"]
    )
    first_time_backfill = document_pipeline.extracted_text_changed(
        [], "\n\n".join(["page one", "page two"]), ["page one", "page two"]
    )
    legacy_content_changed = document_pipeline.extracted_text_changed(
        [], "old extraction", ["new extraction"]
    )

    assert changed_pages is True
    assert unchanged_pages is False
    assert first_time_backfill is False
    assert legacy_content_changed is True


def test_native_backfill_extracts_text_without_ocr_and_skips_scanned_pages():
    native_doc = document_pipeline.fitz.open()
    page = native_doc.new_page()
    page.insert_text((72, 72), "Native page text is long enough for safe page indexing.")
    native_bytes = native_doc.tobytes()
    native_doc.close()

    scanned_doc = document_pipeline.fitz.open()
    scanned_doc.new_page()
    scanned_bytes = scanned_doc.tobytes()
    scanned_doc.close()

    assert document_pipeline.extract_native_pdf_pages(native_bytes) == [
        "Native page text is long enough for safe page indexing."
    ]
    assert document_pipeline.extract_native_pdf_pages(scanned_bytes) is None

def test_document_pipeline_has_no_anthropic_provider_reference():
    from pathlib import Path
    source = Path("document_pipeline.py").read_text(encoding="utf-8")
    assert "Claude" not in source
    assert "Anthropic" not in source
    assert "OpenAI" in source
