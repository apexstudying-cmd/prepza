"""Guard gamification progress, streak, and study-time screens during extraction."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
SCREENS = ROOT / "frontend/src/screens/gamification/ProgressScreens.tsx"
TYPES = ROOT / "frontend/src/types/gamification.ts"
FORMATTER = ROOT / "frontend/src/lib/studyTime.ts"


def test_progress_screens_are_module_owned_and_routes_keep_the_same_props():
    assert "import { XPProgressScreen, StudyStreakScreen, TimeStudiedScreen } from './screens/gamification/ProgressScreens'" in APP
    for name in ("XPProgressScreen", "StudyStreakScreen", "TimeStudiedScreen"):
        assert f"function {name}(" not in APP
    assert "case 'xp-progress':" in APP
    assert "case 'study-streak':" in APP
    assert "case 'time-studied':" in APP


def test_xp_progress_keeps_pagination_and_api_contract():
    source = SCREENS.read_text(encoding="utf-8")
    for contract in (
        "api<XpProgressResponse>('/xp/progress?page=1')",
        "`/xp/progress?page=${nextPage}`",
        "res.history.length >= 20",
        "setHistory(prev => [...prev, ...res.history])",
        "setScreen('profile')",
        "formatXpDate(h.created_at)",
    ):
        assert contract in source


def test_streak_keeps_month_navigation_calendar_and_share_behavior():
    source = SCREENS.read_text(encoding="utf-8")
    for contract in (
        "api<StreakResponse>('/streak' + (viewMonth ? `?month=${viewMonth}` : ''))",
        "setViewMonth(res.calendar_month)",
        "setSelectedDay",
        "formatStudyDuration(d.study_seconds)",
        "setScreen('share-sheet')",
        "setScreen('profile')",
    ):
        assert contract in source


def test_study_time_keeps_period_filter_api_and_share_behavior():
    source = SCREENS.read_text(encoding="utf-8")
    for contract in (
        "useState<'day' | 'week' | 'month'>('week')",
        "api<StudyTimeResponse>(`/study-time?period=${period}`)",
        "formatStudyTime(data.total_seconds)",
        "setScreen('share-sheet')",
        "setScreen('profile')",
    ):
        assert contract in source


def test_gamification_response_types_and_shared_time_formatter_are_preserved():
    types = TYPES.read_text(encoding="utf-8")
    formatter = FORMATTER.read_text(encoding="utf-8")
    for contract in (
        "export type XpHistoryItem =",
        "export type HowToEarnItem =",
        "export type XpProgressResponse =",
        "export type StreakCalendarDay =",
        "export type StreakMilestone =",
        "export type StreakResponse =",
        "export type StudyTimeResponse =",
    ):
        assert contract in types
    assert "export function formatStudyTime(totalSeconds: number)" in formatter
    assert "type StudyTimeResponse =" not in APP
