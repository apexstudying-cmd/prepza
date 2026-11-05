"""Guard the existing chat options screen while moving it behind a feature-owned module."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
SCREEN_PATH = ROOT / "frontend/src/screens/chat/ChatOptionsScreen.tsx"
TYPES_PATH = ROOT / "frontend/src/types/chat.ts"


def test_chat_options_screen_is_module_owned_and_route_composition_is_unchanged():
    assert "import ChatOptionsScreen from './screens/chat/ChatOptionsScreen'" in APP
    assert "function ChatOptionsScreen(" not in APP
    assert "case 'chat-options':" in APP
    assert 'backScreen="chats"' in APP
    assert "setActiveProfileUserId={setActiveProfileUserId}" in APP
    assert "setActiveProfileName={setActiveProfileName}" in APP


def test_chat_options_keeps_existing_api_and_csrf_contracts():
    source = SCREEN_PATH.read_text(encoding="utf-8")
    for contract in (
        "api<{ id: number; csrf_token: string }>('/me')",
        "/chats/${conversationId}",
        "/messages/search?q=${encodeURIComponent(q)}",
        "/attachments",
        "method: 'PATCH'",
        "method: 'POST'",
        "'X-CSRF-Token': csrfToken",
        "JSON.stringify({ name: renameVal.trim() })",
        "JSON.stringify({ muted: next })",
    ):
        assert contract in source


def test_chat_options_preserves_search_media_and_navigation_behavior():
    source = SCREEN_PATH.read_text(encoding="utf-8")
    for contract in (
        "}, 300)",
        "clearTimeout(t)",
        "sharedMediaCategory(item)",
        "setScreen('chats')",
        "setScreen('student-profile')",
        "event.key === 'Escape'",
        "setShowRename(false); setShowSearch(false); setShowMedia(false)",
    ):
        assert contract in source


def test_chat_domain_types_are_shared_without_changing_their_shapes():
    types = TYPES_PATH.read_text(encoding="utf-8")
    for contract in (
        "export type MessageAttachmentData = { id: number; file_type: string; original_filename: string; file_size_bytes: number; view_url: string | null }",
        "export type ChatMessageData = {",
        "export type ChatDetail = { id: number; is_group: boolean; name: string; created_by: number; created_by_name: string; member_count: number; participants: { user_id: number; display_name: string; role: string }[]; viewer_muted: boolean }",
    ):
        assert contract in types
    assert "type ChatDetail =" not in APP
