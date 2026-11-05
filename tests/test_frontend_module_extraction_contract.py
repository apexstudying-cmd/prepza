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
        "'X-CSRF-Token': csrfToken",
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
        "'X-CSRF-Token': csrfToken",
        "userVisibleOnly: true",
        "subscription.unsubscribe()",
    ):
        assert contract in source

def test_podcast_library_screen_is_owned_by_a_feature_module():
    assert "import PodcastLibraryScreen from './screens/podcast/PodcastLibraryScreen'" in APP
    assert "function PodcastLibraryScreen(" not in APP
    assert "case 'podcast-library':" in APP
    assert "DelayedScreenSkeleton={DelayedScreenSkeleton}" in APP
    assert "SkeletonPodcastLibrary={SkeletonPodcastLibrary}" in APP
    assert "EmptyState={EmptyState}" in APP
    assert "ErrorState={ErrorState}" in APP
    assert "PODCAST_LIBRARY_CACHE" not in APP


def test_podcast_library_preserves_fetch_cache_and_navigation_contract():
    source = (
        ROOT / "frontend" / "src" / "screens" / "podcast" /
        "PodcastLibraryScreen.tsx"
    ).read_text(encoding="utf-8")
    for contract in (
        "PODCAST_LIBRARY_CACHE",
        "api<{ podcasts: PodcastItem[] }>('/podcasts')",
        "setPodcastList(res.podcasts)",
        "setActiveDocumentId(p.document_id)",
        "setScreen('podcast-player')",
        "setScreen('home')",
        "Study Podcasts",
        "AI-generated from your notes",
        "Processing…",
        "podcastDuration(p.duration_seconds)",
    ):
        assert contract in source


def test_podcast_metadata_helpers_are_shared_by_home_and_library():
    source = (
        ROOT / "frontend" / "src" / "types" / "podcast.ts"
    ).read_text(encoding="utf-8")
    for contract in (
        "export type PodcastItem",
        "export const podcastColor",
        "export const podcastDuration",
        "Math.max(1, Math.round(seconds / 60))",
    ):
        assert contract in source
    assert "from './types/podcast'" in APP

def test_achievements_screen_is_owned_by_a_gamification_module():
    assert "import AchievementsScreen from './screens/gamification/AchievementsScreen'" in APP
    assert "function AchievementsScreen(" not in APP
    assert "case 'achievements':" in APP
    assert "from './types/achievements'" in APP
    assert "function formatAchievementDate(" not in APP
    assert "type Achievement =" not in APP


def test_achievements_screen_preserves_load_share_and_navigation_contracts():
    source = (
        ROOT / "frontend" / "src" / "screens" / "gamification" /
        "AchievementsScreen.tsx"
    ).read_text(encoding="utf-8")
    assert "export default function AchievementsScreen" in source
    assert "setScreen: (s: 'profile' | 'share-sheet') => void" in source
    for contract in (
        "api<AchievementsResponse>('/achievements')",
        "let cancelled = false",
        "if (!cancelled) setAchievementsList(res.achievements)",
        "const unlocked = achievementsList.filter(a => a.done)",
        "const locked = achievementsList.filter(a => !a.done)",
        "formatAchievementDate(a.unlocked_at)",
        "setScreen('profile')",
        "setScreen('share-sheet')",
        "Achievement Unlocked",
        "Join me on Prepza",
        "<Pill",
    ):
        assert contract in source


def test_achievement_types_keep_the_profile_and_screen_response_contract():
    source = (
        ROOT / "frontend" / "src" / "types" / "achievements.ts"
    ).read_text(encoding="utf-8")
    for contract in (
        "export type Achievement",
        "unlocked_at: string | null",
        "progress: number",
        "total: number",
        "export type AchievementsResponse",
        "achievements: Achievement[]",
    ):
        assert contract in source



def test_my_study_screen_is_owned_by_a_feature_module():
    assert "import StudyMaterialsScreen from './screens/study/StudyMaterialsScreen'" in APP
    assert "function StudyMaterialsScreen(" not in APP
    assert "function mergeStudyMaterialRows(" not in APP
    assert "case 'study-materials':" in APP
    assert "LoadingView={GenerationLoading}" in APP
    assert "ErrorView={GenerationError}" in APP
    assert "EmptyStateView={EmptyState}" in APP


def test_my_study_module_preserves_existing_online_offline_and_replay_contracts():
    source = (
        ROOT / "frontend" / "src" / "screens" / "study" / "StudyMaterialsScreen.tsx"
    ).read_text(encoding="utf-8")
    for contract in (
        "listSavedStudyHubOffline",
        "listOfflineGeneratedMaterials",
        "setOfflineUserId",
        "api<{ id?: number; csrf_token?: string }>('/me')",
        "api<{ saved: SavedStudyLibraryItem[] }>('/library/saved')",
        "api<{ documents: StudyHubDocument[] }>('/documents')",
        "prepza-open-material",
        "setScreen('document-study')",
        "setScreen('upload')",
        "mergeStudyMaterialRows",
        "onRememberLastStudyDocument",
    ):
        assert contract in source


def test_my_study_extraction_does_not_change_the_existing_study_material_route():
    assert "case 'study-materials':" in APP
    assert "setActiveDocumentId={setActiveDocumentId}" in APP
    assert "setScreen={setScreen}" in APP


def test_last_study_resume_transform_updates_extracted_my_study_module(tmp_path):
    import subprocess
    import sys

    root = tmp_path
    (root / "tools").mkdir()
    (root / "frontend" / "src" / "screens" / "study").mkdir(parents=True)
    script = ROOT / "tools" / "apply_last_study_resume.py"
    (root / "tools" / "apply_last_study_resume.py").write_text(
        script.read_text(encoding="utf-8"), encoding="utf-8"
    )
    app = (
        "import StudyMaterialsScreen from './screens/study/StudyMaterialsScreen'\n"
        "// ─── HOME ─────────────────────────────────────────────────────────────────────\n"
        "  const featuredDoc = activeDocs[0]\n"
        "  const restDocs = activeDocs.slice(1)\n"
        "case 'study-materials': return <StudyMaterialsScreen setScreen={setScreen} setActiveDocumentId={setActiveDocumentId} />\n"
        "function DocumentStudyScreen({ setScreen, activeDocumentId }: { setScreen: (s: Screen) => void; activeDocumentId: number | null }) {\n"
        "  useEffect(() => { return () => {} }, [])\n"
        "}\n"
    )
    module = """const openDocument = (id: number) => { setActiveDocumentId(id); setScreen('document-study') }
    """
    (root / "frontend" / "src" / "App.tsx").write_text(app, encoding="utf-8")
    (root / "frontend" / "src" / "screens" / "study" / "StudyMaterialsScreen.tsx").write_text(
        module, encoding="utf-8"
    )
    subprocess.run([sys.executable, str(root / "tools" / "apply_last_study_resume.py")], check=True)
    transformed_app = (root / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
    transformed_module = (
        root / "frontend" / "src" / "screens" / "study" / "StudyMaterialsScreen.tsx"
    ).read_text(encoding="utf-8")
    assert "onRememberLastStudyDocument={rememberLastStudyDocument}" in transformed_app
    assert "onRememberLastStudyDocument?.(id)" in transformed_module
    subprocess.run([sys.executable, str(root / "tools" / "apply_last_study_resume.py")], check=True)
    assert transformed_app.count("onRememberLastStudyDocument={rememberLastStudyDocument}") == 1
    assert transformed_module.count("onRememberLastStudyDocument?.(id)") == 1


def test_library_my_study_transform_supports_extracted_screen_module_and_is_idempotent(tmp_path):
    import shutil
    import subprocess
    import sys

    root = tmp_path
    (root / "tools").mkdir()
    (root / "frontend" / "src" / "screens" / "study").mkdir(parents=True)
    shutil.copyfile(
        ROOT / "tools" / "apply_library_my_study_separation.py",
        root / "tools" / "apply_library_my_study_separation.py",
    )
    shutil.copyfile(ROOT / "frontend" / "src" / "App.tsx", root / "frontend" / "src" / "App.tsx")
    shutil.copyfile(
        ROOT / "frontend" / "src" / "screens" / "study" / "StudyMaterialsScreen.tsx",
        root / "frontend" / "src" / "screens" / "study" / "StudyMaterialsScreen.tsx",
    )
    subprocess.run([sys.executable, str(root / "tools" / "apply_library_my_study_separation.py")], check=True)
    transformed_app = (root / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
    module = (root / "frontend" / "src" / "screens" / "study" / "StudyMaterialsScreen.tsx").read_text(encoding="utf-8")
    assert "useState<'Browse' | 'Published'>" in transformed_app
    assert "activeTab === 'Saved'" not in transformed_app
    assert "saveActionError" in transformed_app
    assert "Saved from Prepza Library" in module
    assert "function StudyMaterialsScreen(" not in transformed_app
    subprocess.run([sys.executable, str(root / "tools" / "apply_library_my_study_separation.py")], check=True)


def test_login_screen_is_owned_by_an_auth_feature_module():
    assert "import LoginScreen from './screens/auth/LoginScreen'" in APP
    assert "case 'login':" in APP
    assert "<LoginScreen setScreen={setScreen} oauthError={oauthError} />" in APP
    assert "function LoginScreen(" not in APP


def test_login_screen_preserves_existing_auth_and_navigation_contracts():
    source = (ROOT / "frontend" / "src" / "screens" / "auth" / "LoginScreen.tsx").read_text(encoding="utf-8")
    assert "export default function LoginScreen" in source
    for contract in (
        "api('/login'",
        "api<{ message: string }>('/resend-verification'",
        "window.location.href = '/auth/google'",
        "setScreen('home')",
        "setScreen('forgot-password')",
        "setScreen('signup')",
        "autoComplete=\"email\"",
        "autoComplete=\"current-password\"",
        "aria-label=\"Continue with Google\"",
    ):
        assert contract in source
