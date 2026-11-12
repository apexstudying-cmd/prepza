from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
SCREEN_PATH = ROOT / "frontend/src/screens/chat/ChatDetailScreen.tsx"
SCREEN = SCREEN_PATH.read_text(encoding="utf-8") if SCREEN_PATH.exists() else ""


def test_active_chat_detail_route_is_owned_by_the_chat_feature_module() -> None:
    assert "import ChatDetailScreen from './screens/chat/ChatDetailScreen'" in APP
    assert "case 'chat-detail':" in APP
    assert "return <ChatDetailScreen" in APP
    assert "function ChatDetailScreen(" not in APP
    assert "export default function ChatDetailScreen(" in SCREEN
    assert "conversationId={activeConversationId}" in APP
    assert "loadingView={<DelayedScreenSkeleton><SkeletonChatDetail /></DelayedScreenSkeleton>}" in APP


def test_chat_detail_preserves_message_api_and_csrf_contracts() -> None:
    for contract in (
        "`/chats/${conversationId}`",
        "`/chats/${conversationId}/messages`",
        "`/chats/${conversationId}/read`",
        "`/chats/${conversationId}/attachments`",
        "`/chats/${conversationId}/attachments/${init.attachment_id}/uploaded`",
        "`/chats/${conversationId}/messages?before_id=${msgs[0].id}`",
        "`/chats/${conversationId}/messages/search?q=${encodeURIComponent(q)}`",
        "'X-CSRF-Token': token",
        "kind: 'reaction'",
        "kind: 'text'",
        "attachment_id: init.attachment_id",
        "getChatCsrfToken",
    ):
        assert contract in SCREEN, f"missing Chat Detail API contract: {contract}"


def test_chat_detail_preserves_realtime_and_lifecycle_contracts() -> None:
    for contract in (
        "joinRealtimeChat(conversationId)",
        "leaveRealtimeChat(conversationId)",
        "sendReadRealtime(conversationId)",
        "sendTypingRealtime(conversationId, false)",
        "prepza-realtime-message",
        "prepza-realtime-read",
        "prepza-realtime-typing",
        "prepza-realtime-presence",
        "typingTimeouts.current.forEach",
        "typingTimeouts.current.clear()",
        "prepza-start-call",
        "prepza-chat-draft-changed",
        "CHAT_DETAIL_CACHE",
    ):
        assert contract in SCREEN, f"missing Chat Detail lifecycle contract: {contract}"


def test_chat_detail_preserves_attachment_voice_and_message_interactions() -> None:
    for contract in (
        "getFileExtension(file.name)",
        "allowedUploadExtensions",
        "maxChatAttachmentSizeBytes",
        "20 MB limit",
        "navigator.mediaDevices.getUserMedia",
        "MediaRecorder",
        "voice-note-",
        "Load earlier messages",
        "Reply to message",
        "React to message",
        "ChatVoiceBubble",
        "setActiveProfileUserId",
        "setActiveProfileName",
        "loadingView",
    ):
        assert contract in SCREEN, f"missing Chat Detail UI contract: {contract}"


def test_e2ee_lifecycle_validator_targets_the_extracted_route_module() -> None:
    validator = (ROOT / "scripts/validate_e2ee_lifecycle.py").read_text(encoding="utf-8")
    assert "frontend/src/screens/chat/ChatDetailScreen.tsx" in validator
    assert '"function ChatDetailScreen"' not in validator
