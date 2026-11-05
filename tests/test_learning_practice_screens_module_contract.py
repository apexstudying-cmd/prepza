"""Guard active flashcard and quiz screens while moving them into a study module."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
SCREENS = ROOT / "frontend/src/screens/study/LearningPracticeScreens.tsx"
TYPES = ROOT / "frontend/src/types/learning.ts"
UI = ROOT / "frontend/src/ui/StudyGenerationStates.tsx"


def test_flashcards_and_quiz_are_module_owned_without_route_changes():
    assert "import { FlashcardsScreen, QuizScreen } from './screens/study/LearningPracticeScreens'" in APP
    assert "function FlashcardsScreen(" not in APP
    assert "function QuizScreen(" not in APP
    assert "case 'flashcards':        return <FlashcardsScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />" in APP
    assert "case 'quiz':              return <QuizScreen setScreen={setScreen} activeDocumentId={activeDocumentId} />" in APP


def test_flashcards_preserve_generation_loading_heartbeat_and_completion_contract():
    source = SCREENS.read_text(encoding="utf-8")
    for contract in (
        "api<{ csrf_token: string }>('/me')",
        "api('/study-time/heartbeat'",
        "JSON.stringify({ feature: 'flashcards' })",
        "api<CompletionResponse>(`/documents/${activeDocumentId}/flashcards/${materialId}/complete`",
        "JSON.stringify({ cards_reviewed: reviewedCount })",
        "'X-CSRF-Token': csrfToken",
        "setScreen('document-study')",
        "setFinished(true)",
    ):
        assert contract in source


def test_quiz_preserves_generation_loading_heartbeat_and_completion_contract():
    source = SCREENS.read_text(encoding="utf-8")
    for contract in (
        "api<{ csrf_token: string }>('/me')",
        "api('/study-time/heartbeat'",
        "JSON.stringify({ feature: 'quiz' })",
        "api<CompletionResponse>(`/documents/${activeDocumentId}/quiz/${materialId}/complete`",
        "JSON.stringify({ score_percent: scorePercent })",
        "'X-CSRF-Token': csrfToken",
        "setScreen('document-study')",
        "setDone(true)",
    ):
        assert contract in source


def test_completion_response_shape_is_shared_and_unchanged():
    types = TYPES.read_text(encoding="utf-8")
    assert "export type CompletionResponse = { xp_awarded: number; newly_unlocked_achievements: string[] }" in types
    assert "type CompletionResponse =" not in APP


def test_shared_generation_states_are_extracted_for_app_and_learning_screens():
    app_import = "import { AchievementToast, GenerationError, GenerationLoading } from './ui/StudyGenerationStates'"
    assert app_import in APP
    for name in ("AchievementToast", "GenerationError", "GenerationLoading"):
        assert f"function {name}(" not in APP
        assert f"export function {name}(" in UI
