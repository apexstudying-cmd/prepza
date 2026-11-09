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
    (root / "frontend" / "src" / "screens" / "library").mkdir(parents=True)
    shutil.copyfile(
        ROOT / "tools" / "apply_library_my_study_separation.py",
        root / "tools" / "apply_library_my_study_separation.py",
    )
    shutil.copyfile(ROOT / "frontend" / "src" / "App.tsx", root / "frontend" / "src" / "App.tsx")
    shutil.copyfile(
        ROOT / "frontend" / "src" / "screens" / "study" / "StudyMaterialsScreen.tsx",
        root / "frontend" / "src" / "screens" / "study" / "StudyMaterialsScreen.tsx",
    )
    shutil.copyfile(
        ROOT / "frontend" / "src" / "screens" / "library" / "LibraryScreen.tsx",
        root / "frontend" / "src" / "screens" / "library" / "LibraryScreen.tsx",
    )
    subprocess.run([sys.executable, str(root / "tools" / "apply_library_my_study_separation.py")], check=True)
    transformed_app = (root / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
    module = (root / "frontend" / "src" / "screens" / "study" / "StudyMaterialsScreen.tsx").read_text(encoding="utf-8")
    library = (root / "frontend" / "src" / "screens" / "library" / "LibraryScreen.tsx").read_text(encoding="utf-8")
    assert "useState<'Browse' | 'Published'>" in library
    assert "activeTab === 'Saved'" not in library
    assert "saveActionError" in library
    assert "Saved from Prepza Library" in module
    assert "function StudyMaterialsScreen(" not in transformed_app
    assert "function LibraryScreen(" not in transformed_app
    subprocess.run([sys.executable, str(root / "tools" / "apply_library_my_study_separation.py")], check=True)
    assert (root / "frontend" / "src" / "screens" / "library" / "LibraryScreen.tsx").read_text(encoding="utf-8") == library


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


def test_study_navigation_transform_supports_extracted_splash_and_is_idempotent(tmp_path):
    import shutil
    import subprocess
    import sys

    root = tmp_path
    (root / "scripts").mkdir()
    (root / "frontend" / "src" / "screens" / "onboarding").mkdir(parents=True)
    shutil.copyfile(
        ROOT / "scripts" / "apply_study_navigation_polish.py",
        root / "scripts" / "apply_study_navigation_polish.py",
    )
    app = """import SplashScreen from './screens/onboarding/SplashScreen'
    function readStoredNavigationState() { return null }
    function App() {
      const setScreen = (_screen: string) => {}
      return <SplashScreen setScreen={setScreen} brandline={PREPZA_BRANDLINE} />
    }
    // prepza: study-navigation-polish-v2
    """
    splash = """export default function SplashScreen({ setScreen, brandline }: { setScreen: (s: 'home' | 'complete-profile' | 'login') => void; brandline: string }) {
      const [state, setState] = useState<'checking' | 'retry'>('checking')
      const checkSession = async (attempt = 0): Promise<void> => {
        setState('checking')
        try {
          const me = await api('/me')
          setScreen(me.university_id ? 'home' : 'complete-profile')
        } catch (e) {
          if (e instanceof ApiError && e.status === 401) {
            setScreen('login')
            return
          }
          if (attempt === 0) {
            setTimeout(() => checkSession(1), 1200)
          } else {
            setState('retry')
          }
        }
      }
    }
    """
    (root / "frontend" / "src" / "App.tsx").write_text(app, encoding="utf-8")
    module_path = root / "frontend" / "src" / "screens" / "onboarding" / "SplashScreen.tsx"
    module_path.write_text(splash, encoding="utf-8")

    command = [sys.executable, str(root / "scripts" / "apply_study_navigation_polish.py")]
    subprocess.run(command, cwd=root, check=True)
    transformed_app = (root / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
    transformed_module = module_path.read_text(encoding="utf-8")
    assert "resumeOffline={() =>" in transformed_app
    assert "const resumeable: Screen[]" in transformed_app
    assert "resumeOffline()" in transformed_module
    assert "brandline, resumeOffline" in transformed_module
    assert "typeof navigator !== 'undefined' && !navigator.onLine" in transformed_module

    subprocess.run(command, cwd=root, check=True)
    assert (root / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8") == transformed_app
    assert module_path.read_text(encoding="utf-8") == transformed_module


def test_edit_profile_screen_is_owned_by_a_profile_feature_module():
    assert "import EditProfileScreen from './screens/profile/EditProfileScreen'" in APP
    assert "case 'edit-profile':" in APP
    assert "function EditProfileScreen(" not in APP


def test_edit_profile_module_preserves_profile_and_avatar_contracts():
    source = (
        ROOT / "frontend" / "src" / "screens" / "profile" / "EditProfileScreen.tsx"
    ).read_text(encoding="utf-8")
    for contract in (
        "api<EditProfileMe>('/me')",
        "api<UniversityOption[]>('/universities')",
        "api<ProgramOption[]>(",
        "'/profile/avatar'",
        "'/profile/avatar/confirm'",
        "'X-CSRF-Token':csrfToken",
        "createImageBitmap(file)",
        "canvas.width = 512",
        "canvas.height = 512",
        "'image/webp', 0.82",
        "blob.size > 512 * 1024",
        "cacheAvatar(id, confirmed.avatar_url)",
        "clearCachedAvatar(id)",
        "method: 'PATCH'",
        "prepza:academic-context-changed",
        "setScreen('profile')",
    ):
        assert contract in source


def test_new_chat_screen_is_owned_by_a_chat_feature_module():
    assert "import NewChatScreen from './screens/chat/NewChatScreen'" in APP
    assert "case 'new-chat':" in APP
    assert "setActiveConversationId={setActiveConversationId}" in APP
    assert "function NewChatScreen(" not in APP


def test_new_chat_module_preserves_search_direct_chat_and_group_creation_contracts():
    source = (
        ROOT / "frontend" / "src" / "screens" / "chat" / "NewChatScreen.tsx"
    ).read_text(encoding="utf-8")
    for contract in (
        "api<{ csrf_token: string }>('/me')",
        "/users/search?q=",
        "}, 300)",
        "clearTimeout(t)",
        "api<{ id: number; reused: boolean }>('/chats', {",
        "is_group: false",
        "participant_ids: [userId]",
        "is_group: true",
        "participant_ids: selectedIds",
        "'X-CSRF-Token': csrfToken",
        "setActiveConversationId(res.id)",
        "setScreen('chat-detail')",
        "setMode('new-chat')",
        "setMode('new-group')",
        "Create Group",
        "<Avi",
    ):
        assert contract in source


def test_student_profile_screen_is_owned_by_the_profile_feature_module():
    assert "import StudentProfileScreen from './screens/profile/StudentProfileScreen'" in APP
    assert "case 'student-profile':" in APP
    assert "function StudentProfileScreen(" not in APP


def test_student_profile_module_preserves_follow_privacy_and_message_contracts():
    source = (
        ROOT / "frontend" / "src" / "screens" / "profile" / "StudentProfileScreen.tsx"
    ).read_text(encoding="utf-8")
    for contract in (
        "/public-profile",
        "/follow-summary",
        "method: 'DELETE'",
        "method: 'POST'",
        "'X-CSRF-Token': csrfToken",
        "is_pending",
        "is_private",
        "api<{ id: number; reused: boolean }>('/chats', {",
        "participant_ids: [targetUserId]",
        "setActiveConversationId?.(res.id)",
        "setScreen('chat-detail')",
        "setScreen('chat-options')",
        "formatStudyTime(profile.weekly_study_seconds)",
        "followers_count",
        "following_count",
        "documents_count",
    ):
        assert contract in source


def test_time_studied_screen_is_owned_by_the_gamification_module():
    assert "import TimeStudiedScreen from './screens/gamification/TimeStudiedScreen'" in APP
    assert "case 'time-studied':" in APP
    assert "function TimeStudiedScreen(" not in APP


def test_time_studied_module_preserves_period_selection_and_loading_contract():
    source = (
        ROOT / "frontend" / "src" / "screens" / "gamification" / "TimeStudiedScreen.tsx"
    ).read_text(encoding="utf-8")
    for contract in (
        "useState<'day' | 'week' | 'month'>('week')",
        "`/study-time?period=${period}`",
        "api<StudyTimeResponse>",
        "if (!cancelled) setData(res)",
        "if (!cancelled) setError",
        "return () => { cancelled = true }",
        "formatStudyTime(data.total_seconds)",
        "setScreen('profile')",
    ):
        assert contract in source


def test_share_opportunity_form_is_owned_by_the_opportunities_module():
    assert "import ShareOppForm from './screens/opportunities/ShareOppForm'" in APP
    assert "case 'share-opp-form':" in APP
    assert "function ShareOppForm(" not in APP


def test_share_opportunity_form_preserves_existing_local_form_fields_and_navigation():
    source = (
        ROOT / "frontend" / "src" / "screens" / "opportunities" / "ShareOppForm.tsx"
    ).read_text(encoding="utf-8")
    for contract in (
        "title: '', org: '', type: 'Internship', deadline: '', location: '', reward: '', desc: '', link: ''",
        "setScreen('create-modal')",
        "setScreen('opportunities')",
        "['Internship','Scholarship','Competition','Job','Event']",
        "Describe the opportunity, requirements, and how to apply...",
        "value={form.desc}",
        "onChange={upd('desc')}",
    ):
        assert contract in source


def test_study_streak_screen_is_owned_by_the_gamification_module():
    assert "import StudyStreakScreen from './screens/gamification/StudyStreakScreen'" in APP
    assert "case 'study-streak':" in APP
    assert "function StudyStreakScreen(" not in APP


def test_study_streak_module_preserves_calendar_loading_navigation_and_milestones():
    source = (
        ROOT / "frontend" / "src" / "screens" / "gamification" / "StudyStreakScreen.tsx"
    ).read_text(encoding="utf-8")
    for contract in (
        "api<StreakResponse>('/streak' + (viewMonth ? `?month=${viewMonth}` : ''))",
        "if (cancelled) return",
        "return () => { cancelled = true }",
        "setSelectedDay(isSelected ? null : d)",
        "setViewMonth(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`)",
        "setScreen('profile')",
        "setScreen('share-sheet')",
        "milestones.filter(m => m.done)",
        "formatStudyDuration(d.study_seconds)",
    ):
        assert contract in source


def test_profile_screen_is_owned_by_the_profile_feature_module():
    assert "import ProfileScreen from './screens/profile/ProfileScreen'" in APP
    assert "case 'profile':" in APP
    assert "function ProfileScreen(" not in APP


def test_profile_module_preserves_profile_data_tabs_cache_and_navigation_contracts():
    source = (
        ROOT / "frontend" / "src" / "screens" / "profile" / "ProfileScreen.tsx"
    ).read_text(encoding="utf-8")
    for contract in (
        "api<ProfileMe>('/me')",
        "api<GamificationSummary>('/gamification/summary')",
        "api<AchievementsResponse>('/achievements')",
        "api<StudyTimeResponse>('/study-time?period=week')",
        "api<{ requests: unknown[] }>('/follow-requests')",
        "api<{ saved: any[] }>('/opportunities/saved')",
        "api<any>('/study-time?period=week')",
        "api<any>('/study-time?period=month')",
        "api<{ documents: HomeDocument[] }>('/documents')",
        "return () => { cancelled = true }",
        "['saved','activity','materials']",
        "setScreen('follow-requests')",
        "setScreen('edit-profile')",
        "setScreen('share-sheet')",
        "setScreen('study-activity')",
        "setScreen('document-study')",
        "PROFILE_CACHE.me",
        "data-prepza-profile-menu",
        "type ProfileScreenRoute =",
        "as ProfileScreenRoute",
    ):
        assert contract in source


def test_document_ready_screen_is_owned_by_the_study_module():
    assert "import DocReadyScreen from './screens/study/DocReadyScreen'" in APP
    assert "case 'doc-ready':" in APP
    assert "function DocReadyScreen(" not in APP


def test_document_ready_module_preserves_document_metadata_and_action_destinations():
    source = (
        ROOT / "frontend" / "src" / "screens" / "study" / "DocReadyScreen.tsx"
    ).read_text(encoding="utf-8")
    for contract in (
        "api<DocumentDetail>(`/documents/${activeDocumentId}`)",
        "setScreen(a.dest)",
        "Document Ready ✓",
        "Processing Complete!",
        "Your document is ready to study",
        "Study with AI",
        "Ask Questions",
        "Summarize",
        "Generate Quiz",
        "Flashcards",
        "Create Podcast",
        "Save to Library",
        "file_size_bytes",
        "page_count",
        "TopBar",
    ):
        assert contract in source


def test_publish_library_screen_remains_in_the_app_shell_until_a_safe_extraction():
    # This screen has not been extracted yet. Keep its existing route and implementation
    # explicit rather than asserting a module that does not exist.
    assert "case 'publish-library':" in APP
    assert "function PublishLibraryScreen(" in APP
    assert "import PublishLibraryScreen from './screens/library/PublishLibraryScreen'" not in APP


def test_publish_library_screen_preserves_document_eligibility_rights_and_submission_contract():
    # The current screen remains inline in App.tsx; assert its real implementation
    # contracts without pretending the future extraction has happened.
    for contract in (
        "api<{ csrf_token: string }>('/me')",
        "api<{ documents:",
        "d.status === 'ready' || d.id === activeDocumentId",
        "api<{ publication_id?: number; status?: string; duplicate?: boolean; published?: boolean; message?: string }>('/library/publish'",
        "'X-CSRF-Token': csrfToken",
        "document_id: selectedDocId",
        "title: title.trim()",
        "description: desc.trim() || undefined",
        "material_type: matType",
        "rightsChecked",
        "setScreen('create-modal')",
        "setScreen('upload')",
        "setScreen('home')",
        "setScreen('library')",
        "type PublishableDoc",
        "EmptyState",
    ):
        assert contract in APP



def test_document_study_hub_screen_is_owned_by_its_study_module():
    assert "import DocumentStudyHubScreen from './screens/study/DocumentStudyHubScreen'" in APP
    assert "function DocumentStudyHubScreen(" not in APP
    assert "case 'document-study':" in APP
    assert "LoadingView={GenerationLoading}" in APP
    assert "ErrorView={GenerationError}" in APP


def test_document_study_hub_preserves_online_offline_reading_and_material_replay():
    source = (
        ROOT / "frontend" / "src" / "screens" / "study" /
        "DocumentStudyHubScreen.tsx"
    ).read_text(encoding="utf-8")
    for contract in (
        "listSavedStudyHubOffline",
        "listOfflineGeneratedMaterials",
        "getSavedStudyHubOffline",
        "saveStudyHubDocumentOffline",
        "`/documents/${activeDocumentId}`",
        "`/documents/${activeDocumentId}/reading`",
        "prepza-offline-user-id",
        "prepza-offline-reading:",
        "prepza-open-material",
        "setScreen('study-materials')",
        "setScreen('document-reader')",
        "setScreen('ai-tutor')",
        "setSaveOfflineBusy",
        "setReadingPage",
    ):
        assert contract in source
