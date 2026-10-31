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
        "'X-CSRF-Token':csrfToken",
        "prepza:academic-context-changed",
        "setScreen('home')",
    ):
        assert required in source


def test_settings_screen_is_owned_by_its_feature_module():
    assert "import SettingsScreen from './screens/settings/SettingsScreen'" in APP
    assert "import Pill from './ui/Pill'" in APP
    assert "case 'settings':" in APP
    assert "function SettingsScreen(" not in APP
    assert "function Pill(" not in APP


def test_settings_screen_preserves_existing_account_and_security_contracts():
    source = (
        ROOT / "frontend" / "src" / "screens" / "settings" / "SettingsScreen.tsx"
    ).read_text(encoding="utf-8")
    assert "import { Ic } from '../../ui/icons'" in source
    for endpoint in (
        "/me",
        "/api/opportunity-discovery",
        "/notification-preferences",
        "/change-email",
        "/change-password",
        "/delete-account",
        "/logout",
        "/profile",
    ):
        assert endpoint in source
    for contract in (
        "'X-CSRF-Token':csrfToken",
        "setScreen('edit-profile')",
        "setScreen('subscription')",
        "setScreen('payment-history')",
        "resetToAuth()",
        "TERMS_TEXT",
        "PRIVACY_TEXT",
    ):
        assert contract in source


def test_push_notification_helpers_keep_the_existing_subscription_contract():
    source = (
        ROOT / "frontend" / "src" / "lib" / "pushNotifications.ts"
    ).read_text(encoding="utf-8")
    for contract in (
        "/push/vapid-public-key",
        "/push/subscribe",
        "'X-CSRF-Token':csrfToken",
        "userVisibleOnly: true",
        "subscription.unsubscribe()",
    ):
        assert contract in source



def test_my_study_screen_is_owned_by_its_feature_module():
    assert "import StudyMaterialsScreen from './screens/study/StudyMaterialsScreen'" in APP
    assert "case 'study-materials':" in APP
    assert "function StudyMaterialsScreen(" not in APP
    assert "function mergeStudyMaterialRows(" not in APP


def test_my_study_module_preserves_online_offline_and_library_contracts():
    source = (
        ROOT / "frontend" / "src" / "screens" / "study" / "StudyMaterialsScreen.tsx"
    ).read_text(encoding="utf-8")
    for contract in (
        "listSavedStudyHubOffline",
        "listOfflineGeneratedMaterials",
        "setOfflineUserId",
        "('/me')",
        "('/library/saved')",
        "('/documents')",
        "'X-CSRF-Token':csrfToken",
        "prepza-open-material",
        "setScreen('document-study')",
        "setScreen('upload')",
    ):
        assert contract in source


def test_my_study_material_merge_deduplicates_by_document_and_material_id():
    source = (
        ROOT / "frontend" / "src" / "screens" / "study" / "StudyMaterialsScreen.tsx"
    ).read_text(encoding="utf-8")
    assert "new Set(current.map(row => `${row.documentId}:${row.materialId}`))" in source
    assert "if (seen.has(key)) continue" in source
    assert "setMaterials(current => mergeStudyMaterialRows(current, cachedMaterials))" in source
    assert "setMaterials(current => mergeStudyMaterialRows(current, rows))" in source
