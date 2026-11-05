"""Guard Library screen ownership, API behavior, and its build-time extraction boundary."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
SCREEN_PATH = ROOT / "frontend/src/screens/library/LibraryScreen.tsx"
TYPES_PATH = ROOT / "frontend/src/types/library.ts"
HELPERS_PATH = ROOT / "frontend/src/lib/library.ts"


def test_library_screen_is_module_owned_and_existing_route_dependencies_are_injected():
    assert "import LibraryScreen from './screens/library/LibraryScreen'" in APP
    assert "function LibraryScreen(" not in APP
    assert "case 'library':" in APP
    assert "setScreen={setScreen}" in APP
    assert "setActiveDocumentId={setActiveDocumentId}" in APP
    assert "EmptyState={EmptyState}" in APP
    assert "ErrorState={ErrorState}" in APP


def test_library_screen_keeps_existing_api_and_csrf_contracts():
    source = SCREEN_PATH.read_text(encoding="utf-8")
    for contract in (
        "api<{ csrf_token: string }>('/me')",
        "api<UniversityOption[]>('/universities')",
        "/library/${reportItem.id}/report",
        "`/library?${params.toString()}`",
        "api<{ saved: SavedLibraryItem[] }>('/library/saved')",
        "api<{ submissions: MySubmission[] }>('/library/my-submissions')",
        "`/library/${pub.id}/save`",
        "method: 'DELETE'",
        "method: 'POST'",
        "'X-CSRF-Token': csrfToken",
        "JSON.stringify({ reason: reportReason, details: reportDetails.trim() || undefined })",
    ):
        assert contract in source


def test_library_screen_preserves_filtering_optimistic_save_and_navigation_behavior():
    source = SCREEN_PATH.read_text(encoding="utf-8")
    for contract in (
        "}, search.trim() ? 350 : 0)",
        "prepza:academic-context-changed",
        "setSavedIds(prev => { const next = new Set(prev); isSaved ? next.delete(pub.id) : next.add(pub.id); return next })",
        "setBrowseItems(items => items.map(it => it.id === pub.id ? { ...it, save_count: it.save_count + (isSaved ? -1 : 1) } : it))",
        "setSavedIds(prev => { const next = new Set(prev); isSaved ? next.add(pub.id) : next.delete(pub.id); return next })",
        "saveStudyHubDocumentOffline(Number(result.document_id))",
        "setScreen('publish-library')",
        "setScreen('document-study')",
        "setActiveDocumentId(p.document_id)",
        "window.history.back()",
    ):
        assert contract in source


def test_library_types_and_shared_material_helpers_keep_existing_contracts():
    types = TYPES_PATH.read_text(encoding="utf-8")
    helpers = HELPERS_PATH.read_text(encoding="utf-8")
    for contract in (
        "export type LibraryPublicationSummary =",
        "export type SavedLibraryItem = LibraryPublicationSummary & { saved_at: string | null }",
        "export type MySubmission =",
    ):
        assert contract in types
    assert "export const LIBRARY_MATERIAL_TYPES:" in helpers
    assert "export const materialTypeLabel" in helpers
    assert "from './lib/library'" in APP
    assert "type LibraryPublicationSummary =" not in APP
    assert "type SavedLibraryItem =" not in APP
    assert "type MySubmission =" not in APP
