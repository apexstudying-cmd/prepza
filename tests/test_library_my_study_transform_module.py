"""Guard the Library/My Study prebuild transform when LibraryScreen is module-owned."""

from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/apply_library_my_study_separation.py"


def test_library_my_study_transform_targets_extracted_library_module_and_is_idempotent(tmp_path):
    root = tmp_path
    (root / "tools").mkdir()
    (root / "frontend/src/screens/library").mkdir(parents=True)
    (root / "frontend/src/screens/study").mkdir(parents=True)
    shutil.copyfile(SCRIPT, root / "tools/apply_library_my_study_separation.py")

    app = (
        "import LibraryScreen from './screens/library/LibraryScreen'\n"
        "import StudyMaterialsScreen from './screens/study/StudyMaterialsScreen'\n"
        "case 'library': return <LibraryScreen setScreen={setScreen} />\n"
    )
    library = """function LibraryScreen() {
  const [activeTab, setActiveTab] = useState<'Browse' | 'Saved' | 'Published'>('Browse')
  const [savedIds, setSavedIds] = useState<Set<number>>(new Set())
  const toggleSave = async (pub: LibraryPublicationSummary) => {
    const isSaved = savedIds.has(pub.id)
    try {
      await api('/library/' + pub.id + '/save', { method: 'POST' })
    } catch {
      setSavedIds(prev => { const next = new Set(prev); isSaved ? next.add(pub.id) : next.delete(pub.id); return next })
    }
  }
  return (
    <>
        {(['Browse', 'Saved', 'Published'] as const).map(t => (\n          <button key={t}>{t}</button>\n        ))}
        {activeTab === 'Saved' && (
          <div>Saved Library items</div>
        )}
        {activeTab === 'Published' && (
          <div>Published items</div>
        )}
        {activeTab === 'Browse' && (
          browseLoading ? (
            <div>Loading</div>
          ) : <div>Browse items</div>
        )}
    </>
  )
}
"""
    study = """const savedLibrary = []
    const label = 'Saved from Prepza Library'
    api<{ saved: SavedStudyLibraryItem[] }>('/library/saved')
"""
    (root / "frontend/src/App.tsx").write_text(app, encoding="utf-8")
    (root / "frontend/src/screens/library/LibraryScreen.tsx").write_text(library, encoding="utf-8")
    (root / "frontend/src/screens/study/StudyMaterialsScreen.tsx").write_text(study, encoding="utf-8")

    command = [sys.executable, str(root / "tools/apply_library_my_study_separation.py")]
    subprocess.run(command, check=True)
    transformed_app = (root / "frontend/src/App.tsx").read_text(encoding="utf-8")
    transformed_library = (root / "frontend/src/screens/library/LibraryScreen.tsx").read_text(encoding="utf-8")
    assert transformed_app == app
    assert "useState<'Browse' | 'Published'>" in transformed_library
    assert "activeTab === 'Saved'" not in transformed_library
    assert "saveActionError" in transformed_library
    assert "setSaveActionError(error instanceof ApiError" in transformed_library

    subprocess.run(command, check=True)
    assert (root / "frontend/src/App.tsx").read_text(encoding="utf-8") == app
    assert (root / "frontend/src/screens/library/LibraryScreen.tsx").read_text(encoding="utf-8") == transformed_library


def test_library_material_type_transform_targets_shared_metadata_module_and_is_idempotent(tmp_path):
    root = tmp_path
    (root / "tools").mkdir()
    (root / "frontend/src/lib").mkdir(parents=True)
    shutil.copyfile(
        ROOT / "tools/apply_library_material_type_restriction.py",
        root / "tools/apply_library_material_type_restriction.py",
    )
    app = "import { LIBRARY_MATERIAL_TYPES } from './lib/library'\n"
    helpers = """export const LIBRARY_MATERIAL_TYPES: { value: string; label: string }[] = [
  { value: 'lecture_notes', label: 'Lecture Notes' },
  { value: 'past_paper', label: 'Past Paper' },
  { value: 'summary', label: 'Summary' },
  { value: 'other', label: 'Other' },
]
export const materialTypeLabel = (v: string) => LIBRARY_MATERIAL_TYPES.find(t => t.value === v)?.label ?? v
"""
    (root / "frontend/src/App.tsx").write_text(app, encoding="utf-8")
    (root / "frontend/src/lib/library.ts").write_text(helpers, encoding="utf-8")
    command = [sys.executable, str(root / "tools/apply_library_material_type_restriction.py")]
    subprocess.run(command, check=True)
    transformed = (root / "frontend/src/lib/library.ts").read_text(encoding="utf-8")
    assert "{ value: 'lecture_notes', label: 'Lecture Notes' }" in transformed
    assert "{ value: 'past_paper', label: 'Past Paper' }" in transformed
    assert "value: 'summary'" not in transformed
    assert "value: 'other'" not in transformed
    assert "materialTypeLabel" in transformed
    subprocess.run(command, check=True)
    assert (root / "frontend/src/lib/library.ts").read_text(encoding="utf-8") == transformed
    assert (root / "frontend/src/App.tsx").read_text(encoding="utf-8") == app


def test_library_material_type_transform_keeps_legacy_inline_fallback(tmp_path):
    root = tmp_path
    (root / "tools").mkdir()
    (root / "frontend/src").mkdir(parents=True)
    shutil.copyfile(
        ROOT / "tools/apply_library_material_type_restriction.py",
        root / "tools/apply_library_material_type_restriction.py",
    )
    app = """const LIBRARY_MATERIAL_TYPES: { value: string; label: string }[] = [
  { value: 'lecture_notes', label: 'Lecture Notes' },
  { value: 'past_paper', label: 'Past Paper' },
  { value: 'summary', label: 'Summary' },
  { value: 'other', label: 'Other' },
]
"""
    (root / "frontend/src/App.tsx").write_text(app, encoding="utf-8")
    command = [sys.executable, str(root / "tools/apply_library_material_type_restriction.py")]
    subprocess.run(command, check=True)
    transformed = (root / "frontend/src/App.tsx").read_text(encoding="utf-8")
    assert "value: 'lecture_notes'" in transformed
    assert "value: 'past_paper'" in transformed
    assert "value: 'summary'" not in transformed
    assert "value: 'other'" not in transformed
    subprocess.run(command, check=True)
    assert (root / "frontend/src/App.tsx").read_text(encoding="utf-8") == transformed
