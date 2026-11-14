"""Protect the PublishLibrary prebuild transform after the screen moves to its feature module."""

from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/apply_library_publish_context_ux.py"
MODULE = ROOT / "frontend/src/screens/library/PublishLibraryScreen.tsx"


def test_publish_library_context_transform_targets_module_and_is_idempotent(tmp_path):
    root = tmp_path
    (root / "tools").mkdir()
    (root / "frontend/src/screens/library").mkdir(parents=True)
    shutil.copyfile(SCRIPT, root / "tools/apply_library_publish_context_ux.py")
    shutil.copyfile(MODULE, root / "frontend/src/screens/library/PublishLibraryScreen.tsx")

    app = "import PublishLibraryScreen from './screens/library/PublishLibraryScreen'\n"
    (root / "frontend/src/App.tsx").write_text(app, encoding="utf-8")

    command = [sys.executable, str(root / "tools/apply_library_publish_context_ux.py")]
    subprocess.run(command, check=True)

    transformed = (root / "frontend/src/screens/library/PublishLibraryScreen.tsx").read_text(encoding="utf-8")
    assert "contextChangedFromProfile" in transformed
    assert "api<UniversityOption[]>('/universities')" in transformed
    assert "api<ProgramOption[]>(" in transformed
    assert "university_id: context.university_id" in transformed
    assert "program_id: context.program_id" in transformed
    assert "year: context.year" in transformed
    assert "semester: context.semester" in transformed
    assert (root / "frontend/src/App.tsx").read_text(encoding="utf-8") == app

    subprocess.run(command, check=True)
    assert (root / "frontend/src/screens/library/PublishLibraryScreen.tsx").read_text(encoding="utf-8") == transformed
    assert (root / "frontend/src/App.tsx").read_text(encoding="utf-8") == app
