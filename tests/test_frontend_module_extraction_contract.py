"""Guard the first behaviour-preserving frontend module extraction."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")


def test_app_uses_shared_api_theme_icons_and_onboarding_modules():
    assert "from './lib/appApi'" in APP
    assert "from './theme/theme'" in APP
    assert "from './ui/icons'" in APP
    assert "from './screens/onboarding/CompleteProfileScreen'" in APP
    assert "class ApiError extends Error" not in APP
    assert "async function api<" not in APP
    assert "function useTheme()" not in APP
    assert "const Ic = {" not in APP
    assert "function CompleteProfileScreen(" not in APP


def test_extracted_api_preserves_cookie_json_and_error_contract():
    source = (ROOT / "frontend" / "src" / "lib" / "appApi.ts").read_text(encoding="utf-8")
    assert "credentials: 'include'" in source
    assert "'Content-Type': 'application/json'" in source
    assert "throw new ApiError" in source


def test_extracted_onboarding_preserves_academic_profile_update_contract():
    source = (
        ROOT / "frontend" / "src" / "screens" / "onboarding" /
        "CompleteProfileScreen.tsx"
    ).read_text(encoding="utf-8")
    for required in (
        "university_id:",
        "program_id:",
        "year:",
        "semester:",
        "'X-CSRF-Token': csrfToken",
        "prepza:academic-context-changed",
        "setScreen('home')",
    ):
        assert required in source
