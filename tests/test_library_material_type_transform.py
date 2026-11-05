"""Guard the Library material-type prebuild transform after module extraction."""

from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "apply_library_material_type_restriction.py"


def _run_transform(root: Path) -> None:
    subprocess.run(
        [sys.executable, str(root / "tools" / "apply_library_material_type_restriction.py")],
        check=True,
    )


def _copy_transform(root: Path) -> None:
    (root / "tools").mkdir(parents=True)
    shutil.copyfile(SCRIPT, root / "tools" / "apply_library_material_type_restriction.py")
    (root / "frontend" / "src" / "lib").mkdir(parents=True)
    (root / "frontend" / "src").mkdir(parents=True, exist_ok=True)


def _full_type_definition() -> str:
    return """export const LIBRARY_MATERIAL_TYPES: { value: string; label: string }[] = [
  { value: 'lecture_notes', label: 'Lecture Notes' },
  { value: 'past_paper', label: 'Past Paper' },
  { value: 'summary', label: 'Summary' },
  { value: 'other', label: 'Other' },
]
"""


def test_material_type_transform_targets_extracted_library_helper_and_is_idempotent(tmp_path):
    _copy_transform(tmp_path)
    app = tmp_path / "frontend" / "src" / "App.tsx"
    app.write_text("import { LIBRARY_MATERIAL_TYPES } from './lib/library'\n", encoding="utf-8")
    helper = tmp_path / "frontend" / "src" / "lib" / "library.ts"
    helper.write_text(_full_type_definition(), encoding="utf-8")

    _run_transform(tmp_path)
    transformed = helper.read_text(encoding="utf-8")
    assert "{ value: 'lecture_notes', label: 'Lecture Notes' }" in transformed
    assert "{ value: 'past_paper', label: 'Past Paper' }" in transformed
    assert "summary" not in transformed
    assert "other" not in transformed

    _run_transform(tmp_path)
    assert transformed == helper.read_text(encoding="utf-8")
    assert app.read_text(encoding="utf-8") == "import { LIBRARY_MATERIAL_TYPES } from './lib/library'\n"


def test_material_type_transform_keeps_legacy_inline_app_fallback(tmp_path):
    _copy_transform(tmp_path)
    app = tmp_path / "frontend" / "src" / "App.tsx"
    app.write_text(_full_type_definition(), encoding="utf-8")

    _run_transform(tmp_path)
    transformed = app.read_text(encoding="utf-8")
    assert "{ value: 'lecture_notes', label: 'Lecture Notes' }" in transformed
    assert "{ value: 'past_paper', label: 'Past Paper' }" in transformed
    assert "summary" not in transformed
    assert "other" not in transformed

    _run_transform(tmp_path)
    assert transformed == app.read_text(encoding="utf-8")
