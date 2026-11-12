from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
NAVIGATION = ROOT / "frontend/src/navigation/useAppNavigation.ts"
NAV = NAVIGATION.read_text(encoding="utf-8") if NAVIGATION.exists() else ""
SCREEN_TYPES = ROOT / "frontend/src/types/navigation.ts"
SCREENS = SCREEN_TYPES.read_text(encoding="utf-8") if SCREEN_TYPES.exists() else ""


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
    assert "onResetToLogin?.()" in NAV


def test_app_shell_uses_navigation_hook_and_keeps_session_revalidation() -> None:
    assert "import { useAppNavigation } from './navigation/useAppNavigation'" in APP
    assert "useAppNavigation({ onResetToLogin: resetChatRealtime })" in APP
    assert "function readStoredNavigationState" not in APP
    assert "const [screenStack, setScreenStack]" not in APP
    assert "window.addEventListener('pageshow', onPageShow)" in APP
    assert "api('/me').catch" in APP
    assert "e instanceof ApiError && e.status === 401" in APP


def test_navigation_state_persistence_remains_lifted_in_the_app_shell() -> None:
    assert "sessionStorage.setItem('prepza-navigation-state'" in APP
    for key in ("screenStack", "activeConversationId", "activeDocumentId", "activeGroupId", "activeProfileUserId", "activeOpportunityId"):
        assert key in APP
