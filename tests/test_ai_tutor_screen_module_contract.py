"""Guard Morio's existing AI tutor screen while moving it to a feature-owned module."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
SCREEN = ROOT / "frontend/src/screens/tutor/AITutorScreen.tsx"


def test_ai_tutor_screen_is_module_owned_and_route_props_are_preserved():
    assert "import AITutorScreen from './screens/tutor/AITutorScreen'" in APP
    assert "function AITutorScreen(" not in APP
    assert "case 'ai-tutor':" in APP
    assert "activeDocumentId={activeDocumentId}" in APP
    assert "setActiveDocumentId={setActiveDocumentId}" in APP
    assert "GenerationError={GenerationError}" in APP
    assert "DelayedScreenSkeleton={DelayedScreenSkeleton}" in APP
    assert "SkeletonAITutor={SkeletonAITutor}" in APP


def test_ai_tutor_keeps_document_picker_and_conversation_api_contracts():
    source = SCREEN.read_text(encoding="utf-8")
    for contract in (
        "api<{ documents: PickableDoc[] }>('/documents')",
        "res.documents.filter(d => d.status === 'ready')",
        "api<{ csrf_token: string }>('/me')",
        "`/documents/${activeDocumentId}/tutor`",
        "`/documents/${activeDocumentId}/tutor/messages`",
        "method: 'POST'",
        "'X-CSRF-Token': csrfToken",
        "JSON.stringify({ body })",
        "setMessages(m => [...m, res.reply])",
    ):
        assert contract in source


def test_ai_tutor_keeps_heartbeat_error_handling_and_session_cache():
    source = SCREEN.read_text(encoding="utf-8")
    for contract in (
        "AI_TUTOR_CACHE[activeDocumentId]",
        "AI_TUTOR_CACHE[activeDocumentId] = res.messages",
        "body: JSON.stringify({ feature: 'tutor_chat' })",
        "setInterval(ping, 20000)",
        "e.status === 429",
        "e.status === 503",
        "You've hit the hourly message limit - try again later.",
        "AI budget exceeded for now - try again later.",
    ):
        assert contract in source


def test_ai_tutor_keeps_existing_navigation_and_shared_shell_components():
    source = SCREEN.read_text(encoding="utf-8")
    for contract in (
        "setScreen('home')",
        "setScreen('upload')",
        "<GenerationError error={pickerError} />",
        "<DelayedScreenSkeleton><SkeletonAITutor /></DelayedScreenSkeleton>",
        "Morio",
        "Ask your AI tutor anything…",
    ):
        assert contract in source
    assert "type TutorMsg =" in source
    assert "type PickableDoc =" in source
    assert "const AI_TUTOR_CACHE:" in source
    assert "type TutorMsg =" not in APP
    assert "type PickableDoc =" not in APP
    assert "const AI_TUTOR_CACHE:" not in APP
