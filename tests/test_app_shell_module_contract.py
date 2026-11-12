from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
SHELL = ROOT / "frontend/src/navigation/AppShell.tsx"
SHELL_TEXT = SHELL.read_text(encoding="utf-8") if SHELL.exists() else ""
BOTTOM = ROOT / "frontend/src/navigation/BottomNav.tsx"
BOTTOM_TEXT = BOTTOM.read_text(encoding="utf-8") if BOTTOM.exists() else ""


def test_app_root_delegates_global_chrome_to_app_shell() -> None:
    assert "import AppShell from './navigation/AppShell'" in APP
    assert "<AppShell" in APP
    assert "function BottomNav(" not in APP
    assert "function StudentOnboarding" not in APP
    assert "html[data-prepza-theme=" not in APP
    assert "noNav.includes(screen)" not in APP


def test_app_shell_owns_theme_chrome_and_global_overlays() -> None:
    for contract in (
        "export default function AppShell(",
        "html[data-prepza-theme=\"dark\"]",
        "StudentOnboarding",
        "CallExperience",
        "BottomNav",
        "noNav.includes(screen)",
        "['splash', 'login', 'processing'].includes(screen)",
        "['splash', 'login', 'forgot-password', 'signup', 'check-email', 'complete-profile', 'reset-password', 'verify-confirm'].includes(screen)",
    ):
        assert contract in SHELL_TEXT


def test_bottom_navigation_owns_tab_selection_and_attention_behavior() -> None:
    for contract in (
        "export default function BottomNav(",
        "prepza-last-explore-opportunity-id",
        "prepza-latest-explore-opportunity-id",
        "setExploreAttention?.(false)",
        "aria-label=\"Primary navigation\"",
        "unreadChats",
        "exploreAttention",
    ):
        assert contract in BOTTOM_TEXT


def test_shop_frontend_transform_targets_module_owned_bottom_navigation() -> None:
    transform = (ROOT / "scripts/apply_shop_frontend.py").read_text(encoding="utf-8")
    assert "frontend/src/navigation/BottomNav.tsx" in transform
    assert "document-reader','shop'].includes(active)" in transform
    assert "document-reader','shop'].includes(active)" not in APP
