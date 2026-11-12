from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
READER = (ROOT / "frontend" / "src" / "screens" / "study" / "DocumentReaderScreen.tsx").read_text(encoding="utf-8")


def test_active_document_reader_is_owned_by_the_study_feature_module() -> None:
    assert "import DocumentReaderScreen from './screens/study/DocumentReaderScreen'" in APP
    assert "case 'document-reader': return <DocumentReaderScreen" in APP
    assert "DOC_CACHE={DOC_CACHE}" in APP
    assert "GenerationLoading={GenerationLoading}" in APP
    assert "GenerationError={GenerationError}" in APP
    assert "function DocumentReaderScreen(" not in APP
    assert "export default function DocumentReaderScreen(" in READER


def test_document_reader_preserves_offline_progress_and_heartbeat_contracts() -> None:
    for contract in (
        "getSavedStudyHubOffline",
        "getOfflineStudyDocumentUrl",
        "saveStudyHubDocumentOffline",
        "prepza-offline-user-id",
        "prepza-offline-reading:",
        "`/documents/${activeDocumentId}`",
        "`/documents/${activeDocumentId}/reading`",
        "'/study-time/heartbeat'",
        "feature: 'reading'",
        "'X-CSRF-Token': csrfToken",
        "setInterval(ping, 20000)",
        "setTimeout(",
        "350",
        "IntersectionObserver",
        "data-reader-page",
        "PdfStudyCanvas",
        "storageKey={`offline:",
        "window.history.back()",
        "loading={index < 2 ? 'eager' : 'lazy'}",
        "setZoom",
        "GenerationLoading",
        "GenerationError",
    ):
        assert contract in READER, f"missing reader behavior contract: {contract}"


def test_document_reader_prebuild_transforms_follow_the_extracted_module() -> None:
    progress = (ROOT / "scripts" / "apply_document_study_progress.py").read_text(encoding="utf-8")
    instant = (ROOT / "tools" / "apply_instant_navigation_fixes.py").read_text(encoding="utf-8")
    polish = (ROOT / "scripts" / "apply_study_navigation_polish.py").read_text(encoding="utf-8")
    legacy = (ROOT / "scripts" / "apply_document_reader.py").read_text(encoding="utf-8")
    assert "READER_MODULE" in progress and "READER_MODULE.write_text" in progress
    assert "READER_MODULE" in instant and "reader_path = READER_MODULE" in instant
    assert "READER_MODULE" in polish and "READER_MODULE.write_text" in polish
    assert "reader_module.exists()" in legacy and "if not reader_module.exists()" in legacy


def test_reader_transform_workflows_verify_module_idempotency() -> None:
    polish = (ROOT / ".github" / "workflows" / "study-navigation-polish.yml").read_text(encoding="utf-8")
    navigation = (ROOT / ".github" / "workflows" / "student-navigation-ux.yml").read_text(encoding="utf-8")
    assert "cp frontend/src/screens/study/DocumentReaderScreen.tsx /tmp/DocumentReaderScreen.after" in polish
    assert "cmp frontend/src/screens/study/DocumentReaderScreen.tsx /tmp/DocumentReaderScreen.after" in polish
    assert "cp frontend/src/screens/study/DocumentReaderScreen.tsx /tmp/DocumentReaderScreen.after" in navigation
    assert "cmp frontend/src/screens/study/DocumentReaderScreen.tsx /tmp/DocumentReaderScreen.after" in navigation
