from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "apply_document_study_progress.py"
SPEC = importlib.util.spec_from_file_location("document_study_progress_patch", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_offline_reading_gate_is_updated_in_the_api_module() -> None:
    source = """async function api<T = any>(path: string): Promise<T> {
  const cleanPath = String(path || '')
  if (/^\\/documents\\/\\d+\\/reading$/.test(cleanPath)) return { page_num: 0 } as T
  return {} as T
}"""
    patched = MODULE.patch_offline_reading_gate(source)
    assert "prepza-reading-progress:" in patched
    assert "localStorage.getItem" in patched
    assert "return { page_num } as T" in patched


def test_offline_reading_gate_transform_is_idempotent() -> None:
    source = """async function api<T = any>(path: string): Promise<T> {
  const cleanPath = String(path || '')
  if (/^\\/documents\\/\\d+\\/reading$/.test(cleanPath)) return { page_num: 0 } as T
  return {} as T
}"""
    once = MODULE.patch_offline_reading_gate(source)
    assert MODULE.patch_offline_reading_gate(once) == once


def test_offline_reading_gate_fails_clearly_without_route_anchor() -> None:
    try:
        MODULE.patch_offline_reading_gate("async function api() { return {} }")
    except SystemExit as error:
        assert "offline reading gate anchor not found" in str(error)
    else:
        raise AssertionError("Expected a clear error for a missing reading route")



def test_native_reader_progress_transform_targets_the_extracted_module_contract() -> None:
    source = """export default function DocumentReaderScreen({ activeDocumentId }: { activeDocumentId: number | null }) {
  const [csrfToken, setCsrfToken] = useState('')
  api<{csrf_token:string}>('/me')
  const pageUrl = `/documents/${activeDocumentId}/reading/page/${current}`
}"""
    patched = MODULE.patch_native_reader(source)
    assert "readerUserId" in patched
    assert "prepza-reading-progress:" in patched
    assert "saveLocalPage" in patched
    assert "prepza_user=" in patched
    assert MODULE.patch_native_reader(patched) == patched


def test_native_reader_progress_transform_fails_clearly_without_component() -> None:
    try:
        MODULE.patch_native_reader("export default function OtherScreen() { return null }")
    except SystemExit as error:
        assert "native reader function anchor not found" in str(error)
    else:
        raise AssertionError("Expected a clear error for a missing native reader")
