"""Guard the active XP progress screen and shared study-time contract during extraction."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
SCREEN = ROOT / "frontend/src/screens/gamification/ProgressScreens.tsx"
TYPES = ROOT / "frontend/src/types/gamification.ts"
FORMATTER = ROOT / "frontend/src/lib/studyTime.ts"


def test_xp_progress_screen_is_module_owned_and_route_is_unchanged():
    assert "import { XPProgressScreen } from './screens/gamification/ProgressScreens'" in APP
    assert "function XPProgressScreen(" not in APP
    assert "case 'xp-progress':       return <XPProgressScreen setScreen={setScreen} />" in APP
    # These routes intentionally continue to use the existing StudyActivityScreen.
    assert "case 'study-streak':      return <StudyActivityScreen setScreen={setScreen} />" in APP
    assert "case 'time-studied':      return <StudyActivityScreen setScreen={setScreen} />" in APP


def test_xp_progress_keeps_api_pagination_and_navigation_contracts():
    source = SCREEN.read_text(encoding="utf-8")
    for contract in (
        "api<XpProgressResponse>('/xp/progress?page=1')",
        "`/xp/progress?page=${nextPage}`",
        "res.history.length >= 20",
        "setHistory(prev => [...prev, ...res.history])",
        "setScreen('profile')",
        "formatXpDate(h.created_at)",
    ):
        assert contract in source


def test_gamification_response_types_and_shared_study_time_formatter_are_preserved():
    types = TYPES.read_text(encoding="utf-8")
    formatter = FORMATTER.read_text(encoding="utf-8")
    for contract in (
        "export type XpHistoryItem =",
        "export type HowToEarnItem =",
        "export type XpProgressResponse =",
        "export type StudyTimeResponse =",
    ):
        assert contract in types
    assert "export function formatStudyTime(totalSeconds: number)" in formatter
    assert "type StudyTimeResponse =" not in APP
    assert "function formatStudyTime(" not in APP
    profile_screen = (ROOT / "frontend/src/screens/profile/StudentProfileScreen.tsx").read_text(encoding="utf-8")
    assert "formatStudyTime(profile.weekly_study_seconds)" in profile_screen
