"""Guard the Library screen's existing API, save, report, filter, and route contracts."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
SCREEN_PATH = ROOT / "frontend/src/screens/library/LibraryScreen.tsx"
TYPES_PATH = ROOT / "frontend/src/types/library.ts"
LIBRARY_HELPERS = ROOT / "frontend/src/lib/library.ts"


def test_library_screen_is_owned_by_its_feature_module_and_keeps_route_wiring():
    assert "import LibraryScreen from './screens/library/LibraryScreen'" in APP
    assert "function LibraryScreen(" not in APP
    assert "case 'library':" in APP
    assert "setActiveDocumentId={setActiveDocumentId}" in APP
    assert "EmptyState={EmptyState}" in APP
    assert "ErrorState={ErrorState}" in APP
    assert "import { LIBRARY_MATERIAL_TYPES, materialTypeLabel } from './lib/library'" in APP


def test_library_screen_preserves_existing_api_and_csrf_contracts():
    source = SCREEN_PATH.read_text(encoding="utf-8")
    for contract in (
        "api<{ csrf_token: string }>('/me')",
        "api<UniversityOption[]>('/universities')",
        "`/library/${reportItem.id}/report`",
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


def test_library_screen_preserves_filter_debounce_academic_refresh_and_save_rollback():
    source = SCREEN_PATH.read_text(encoding="utf-8")
    for contract in (
        "prepza:academic-context-changed",
        "search.trim() ? 350 : 0",
        "params.set('material_type', materialTypeFilter)",
        "params.set('university_id', String(universityFilter))",
        "setSavedIds(prev => { const next = new Set(prev); isSaved ? next.delete(pub.id) : next.add(pub.id); return next })",
        "setBrowseItems(items => items.map(it => it.id === pub.id ? { ...it, save_count: it.save_count + (isSaved ? -1 : 1) } : it))",
        "await saveStudyHubDocumentOffline(Number(result.document_id))",
        "setScreen('publish-library')",
        "setScreen('document-study')",
    ):
        assert contract in source


def test_library_domain_types_and_shared_material_labels_keep_existing_shapes():
    types = TYPES_PATH.read_text(encoding="utf-8")
    helpers = LIBRARY_HELPERS.read_text(encoding="utf-8")
    for contract in (
        "export type LibraryPublicationSummary = {",
        "export type SavedLibraryItem = LibraryPublicationSummary & { saved_at: string | null }",
        "export type MySubmission = {",
    ):
        assert contract in types
    assert "export const LIBRARY_MATERIAL_TYPES:" in helpers
    assert "export const materialTypeLabel =" in helpers
    assert "type LibraryPublicationSummary =" not in APP
    assert "type SavedLibraryItem =" not in APP
    assert "type MySubmission =" not in APP


def test_library_screen_uses_injected_shell_states_without_importing_app():
    source = SCREEN_PATH.read_text(encoding="utf-8")
    assert "from '../../ui/Pill'" in source
    assert "from '../../lib/appApi'" in source
    assert "from '../../offline/studyHubOffline'" in source
    assert "EmptyState: ComponentType<" in source
    assert "ErrorState: ComponentType<" in source
    assert "from '../../App'" not in source
