from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
NAVIGATION = ROOT / "frontend/src/navigation/useAppNavigation.ts"
NAV = NAVIGATION.read_text(encoding="utf-8") if NAVIGATION.exists() else ""
SCREEN_TYPES = ROOT / "frontend/src/types/navigation.ts"
SCREENS = SCREEN_TYPES.read_text(encoding="utf-8") if SCREEN_TYPES.exists() else ""
POLISH_PATH = ROOT / "scripts/apply_study_navigation_polish.py"
POLISH_SPEC = importlib.util.spec_from_file_location("apply_study_navigation_polish", POLISH_PATH)
assert POLISH_SPEC and POLISH_SPEC.loader
POLISH = importlib.util.module_from_spec(POLISH_SPEC)
POLISH_SPEC.loader.exec_module(POLISH)


def test_screen_union_is_a_shared_navigation_contract() -> None:
    assert "import type { Screen } from './types/navigation'" in APP
    assert "export type Screen =" in SCREENS
    assert "'shop'" in SCREENS
    assert "type Screen =" not in APP


def test_navigation_hook_preserves_stack_and_browser_history_semantics() -> None:
    assert "export function useAppNavigation(" in NAV
    assert "prepza-navigation-state" in NAV
    assert "storedNavigation?.stack || ['splash']" in NAV
    assert "stack.lastIndexOf(target)" in NAV or "stack.lastIndexOf(s)" in NAV
    assert "window.history.pushState({ prepzaNav: true }, '')" in NAV
    assert "window.history.replaceState({ prepzaNav: true }, window.location.pathname)" in NAV
    assert "window.addEventListener('popstate', onPopState)" in NAV
    assert "stack.length > 1 ? stack.slice(0, -1) : stack" in NAV
    reset_start = NAV.index("const resetNavigation")
    reset_end = NAV.index("\n  useEffect", reset_start)
    reset_navigation = NAV[reset_start:reset_end]
    assert "if (target === 'login') onResetToLogin?.()" in reset_navigation


def test_app_shell_uses_navigation_hook_and_keeps_session_revalidation() -> None:
    assert "import { useAppNavigation } from './navigation/useAppNavigation'" in APP
    assert "useAppNavigation({" in APP
    assert "onResetToLogin: resetChatRealtime" in APP
    assert "function readStoredNavigationState" not in APP
    assert "const [screenStack, setScreenStack]" not in APP
    assert "window.addEventListener('pageshow', onPageShow)" in APP
    assert "api('/me').catch" in APP
    assert "e instanceof ApiError && e.status === 401" in APP


def test_navigation_state_persistence_remains_lifted_in_the_app_shell() -> None:
    assert "sessionStorage.setItem('prepza-navigation-state'" in APP
    for key in ("screenStack", "activeConversationId", "activeDocumentId", "activeGroupId", "activeProfileUserId", "activeOpportunityId"):
        assert key in APP


def test_navigation_polish_targets_the_extracted_hook_and_keeps_back_semantics() -> None:
    hook = """  const setScreen = (target: Screen) => {
    if (target === screen) return
    setScreenStack(stack => {
      const ancestorIndex = stack.lastIndexOf(target)
      return ancestorIndex >= 0 ? stack.slice(0, ancestorIndex + 1) : [...stack, target]
    })
    window.history.pushState({ prepzaNav: true }, '')
  }
"""
    updated = POLISH.harden_document_navigation(hook)
    assert "window.history.back()" in updated
    assert "screenStack[screenStack.length - 2] === target" in updated
    assert "localStorage.getItem('prepza-navigation-state')" in POLISH.persist_navigation_across_restarts("sessionStorage.getItem('prepza-navigation-state')")
    assert "localStorage.setItem('prepza-navigation-state'" in POLISH.persist_navigation_across_restarts("sessionStorage.setItem('prepza-navigation-state', value)")


def test_extracted_splash_resume_uses_the_hook_snapshot_not_a_private_helper() -> None:
    source = POLISH_PATH.read_text(encoding="utf-8")
    assert "NAVIGATION_MODULE = Path('frontend/src/navigation/useAppNavigation.ts')" in source
    assert "const stored = storedNavigation" in source
    assert "const stored = readStoredNavigationState()" in source
    assert "NAVIGATION_MODULE.read_text(encoding='utf-8')" in source
