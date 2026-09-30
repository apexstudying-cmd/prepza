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


def test_document_pipeline_has_no_anthropic_provider_reference():
    from pathlib import Path
    source = Path("document_pipeline.py").read_text(encoding="utf-8")
    assert "Claude" not in source
    assert "Anthropic" not in source
    assert "OpenAI" in source
