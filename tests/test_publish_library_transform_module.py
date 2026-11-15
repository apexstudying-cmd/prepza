"""Protect PublishLibrary transform ownership, idempotency, and existing screen contracts."""

from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/apply_library_publish_context_ux.py"
MODULE = ROOT / "frontend/src/screens/library/PublishLibraryScreen.tsx"

PRESERVED_SCREEN_CONTRACTS = (
    "Free to publish · Shared immediately",
    "Select a document",
    "Publication title",
    "Content responsibility",
    "I confirm that I have the right or permission to share this material",
    "Library moderation",
    "Already in Prepza Library",
    "Go to My Library",
    "Back to Home",
    "setScreen('create-modal')",
    "setScreen('upload')",
    "setScreen('library')",
    "setScreen('home')",
    "selectedDoc?.status === 'ready'",
    "rightsChecked",
    "setStep(4)",
    "setStep(5)",
    "setStep(3)",
    "api<{ csrf_token: string }>('/me')",
    "api<{ documents:",
    "('/documents')",
    "('/library/publish'",
    "headers: { 'X-CSRF-Token': csrfToken }",
    "document_id: selectedDocId",
    "title: title.trim()",
    "description: desc.trim() || undefined",
    "material_type: matType",
    "N.navy",
    "N.gold",
    "T.card",
    "T.pageBg",
)


def run_transform(root: Path) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(root / "tools/apply_library_publish_context_ux.py")]
    return subprocess.run(command, check=True, capture_output=True, text=True)


def assert_publish_screen_contract(source: str) -> None:
    for marker in PRESERVED_SCREEN_CONTRACTS:
        assert marker in source, f"PublishLibrary screen contract disappeared: {marker}"

    # Academic context is added by the existing prebuild transform; the
    # profile update remains an explicit, CSRF-protected user action.
    assert "contextChangedFromProfile" in source
    assert "api<UniversityOption[]>('/universities')" in source
    assert "api<ProgramOption[]>(" in source
    assert "university_id: context.university_id" in source
    assert "program_id: context.program_id" in source
    assert "year: context.year" in source
    assert "semester: context.semester" in source
    assert "await api('/profile', { method: 'PATCH'" in source
    assert "headers: { 'X-CSRF-Token': csrfToken }" in source
    assert "Update my profile" in source


def test_publish_library_context_transform_targets_module_preserves_screen_and_is_idempotent(tmp_path):
    root = tmp_path
    (root / "tools").mkdir()
    (root / "frontend/src/screens/library").mkdir(parents=True)
    shutil.copyfile(SCRIPT, root / "tools/apply_library_publish_context_ux.py")
    shutil.copyfile(MODULE, root / "frontend/src/screens/library/PublishLibraryScreen.tsx")

    app = "import PublishLibraryScreen from './screens/library/PublishLibraryScreen'\\n"
    (root / "frontend/src/App.tsx").write_text(app, encoding="utf-8")

    run_transform(root)

    transformed = (root / "frontend/src/screens/library/PublishLibraryScreen.tsx").read_text(encoding="utf-8")
    assert_publish_screen_contract(transformed)
    assert (root / "frontend/src/App.tsx").read_text(encoding="utf-8") == app

    run_transform(root)
    assert (root / "frontend/src/screens/library/PublishLibraryScreen.tsx").read_text(encoding="utf-8") == transformed
    assert (root / "frontend/src/App.tsx").read_text(encoding="utf-8") == app


def test_publish_library_context_transform_keeps_legacy_app_fallback(tmp_path):
    root = tmp_path
    (root / "tools").mkdir()
    (root / "frontend/src").mkdir(parents=True)
    shutil.copyfile(SCRIPT, root / "tools/apply_library_publish_context_ux.py")

    # Build a legacy inline owner from the same screen source. The fallback is
    # retained for older worktrees where the feature module does not exist.
    legacy = MODULE.read_text(encoding="utf-8")
    legacy = legacy.replace(
        "type LibraryAcademicContext = { university_id: number | null; program_id: number | null; year: number | null; semester: number | null }\\n",
        "",
        1,
    )
    legacy = legacy.replace(
        "import type { PublishableDoc } from '../../types/library'\\n",
        "type PublishableDoc = { id: number; title: string; status: string; file_type: string | null; page_count: number | null }\\n",
        1,
    )
    (root / "frontend/src/App.tsx").write_text(legacy, encoding="utf-8")

    run_transform(root)

    transformed = (root / "frontend/src/App.tsx").read_text(encoding="utf-8")
    assert transformed.count("type LibraryAcademicContext =") == 1
    assert_publish_screen_contract(transformed)
    assert not (root / "frontend/src/screens/library/PublishLibraryScreen.tsx").exists()
