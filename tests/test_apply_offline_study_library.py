from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "apply_offline_study_library.py"
SPEC = importlib.util.spec_from_file_location("offline_study_library_patch", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


SAVE_HOOK = """  // Library save -> offline asset download
  if (method === 'POST' && cleanPath.endsWith('/save')) {
    try {
      body.offline_available = true
    } catch (_) {}
  }
"""


def test_library_save_hook_supports_original_api_return_indentation() -> None:
    source = """async function api<T = any>(path: string): Promise<T> {
  const body: any = {}
  return body as T
}"""
    patched = MODULE.insert_library_save_hook(source, SAVE_HOOK)

    assert patched.index("Library save -> offline asset download") < patched.index("return body as T")
    assert "  // Library save -> offline asset download" in patched
    assert "  return body as T" in patched


def test_library_save_hook_supports_try_catch_wrapped_api_return() -> None:
    source = """async function api<T = any>(path: string): Promise<T> {
  try {
    const body: any = {}
    return body as T
  } catch (error) {
    throw error
  }
}"""
    patched = MODULE.insert_library_save_hook(source, SAVE_HOOK)

    assert patched.index("Library save -> offline asset download") < patched.index("return body as T")
    assert "    // Library save -> offline asset download" in patched
    assert "    if (method === 'POST' && cleanPath.endsWith('/save'))" in patched
    assert "        body.offline_available = true" in patched
    assert "    return body as T" in patched


def test_library_save_hook_is_idempotent() -> None:
    source = """async function api<T = any>(path: string): Promise<T> {
  try {
    const body: any = {}
    return body as T
  } catch (error) {
    throw error
  }
}"""
    once = MODULE.insert_library_save_hook(source, SAVE_HOOK)
    twice = MODULE.insert_library_save_hook(once, SAVE_HOOK)

    assert twice == once


def test_library_save_hook_fails_clearly_without_success_return() -> None:
    source = """async function api<T = any>(path: string): Promise<T> {
  return response as T
}"""

    try:
        MODULE.insert_library_save_hook(source, SAVE_HOOK)
    except SystemExit as error:
        assert "successful API return anchor not found" in str(error)
    else:
        raise AssertionError("Expected a clear failure when the API return cannot be located")
