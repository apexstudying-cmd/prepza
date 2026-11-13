from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "frontend/src/App.tsx"
DETAIL_PATH = ROOT / "frontend/src/screens/chat/ChatDetailScreen.tsx"
APP = APP_PATH.read_text(encoding="utf-8")


def _detail_source() -> str:
    assert DETAIL_PATH.exists(), "active ChatDetailScreen must be owned by its chat feature module"
    return DETAIL_PATH.read_text(encoding="utf-8")


def test_active_chat_detail_route_is_owned_by_the_chat_feature_module() -> None:
    detail = _detail_source()
    assert "import ChatDetailScreen, { getChatDraft } from './screens/chat/ChatDetailScreen'" in APP
    assert "case 'chat-detail':       return <ChatDetailScreen" in APP
    assert "function ChatDetailScreen(" not in APP
    assert "export default function ChatDetailScreen(" in detail
    assert "conversationId={activeConversationId}" in APP
    assert "setActiveProfileUserId={setActiveProfileUserId}" in APP
    assert "setActiveProfileName={setActiveProfileName}" in APP


def test_chat_detail_keeps_existing_api_and_csrf_contracts() -> None:
    detail = _detail_source()
    for contract in (
        "`/chats/${conversationId}`",
        "`/chats/${conversationId}/messages`",
        "`/chats/${conversationId}/read`",
        "`/chats/${conversationId}/messages?before_id=${msgs[0].id}`",
        "`/chats/${conversationId}/messages/search?q=${encodeURIComponent(q)}`",
        "`/chats/${conversationId}/attachments`",
        "`/chats/${conversationId}/attachments/${init.attachment_id}/uploaded`",
        "'X-CSRF-Token'",
        "JSON.stringify(envelope)",
        "fetch(init.upload_url, { method: 'PUT'",
    ):
        assert contract in detail, f"missing ChatDetail API contract: {contract}"


def test_chat_detail_keeps_realtime_presence_typing_and_call_contracts() -> None:
    detail = _detail_source()
    for contract in (
        "joinRealtimeChat(conversationId)",
        "leaveRealtimeChat(conversationId)",
        "sendReadRealtime(conversationId)",
        "sendTypingRealtime(conversationId, false)",
        "'prepza-realtime-message'",
        "'prepza-realtime-read'",
        "'prepza-realtime-typing'",
        "'prepza-realtime-presence'",
        "'prepza-start-call'",
        "window.removeEventListener",
        "typingTimeouts.current.clear()",
    ):
        assert contract in detail, f"missing ChatDetail realtime contract: {contract}"


def test_chat_detail_keeps_drafts_cache_reactions_and_voice_lifecycle() -> None:
    detail = _detail_source()
    for contract in (
        "CHAT_DETAIL_CACHE",
        "prepza-chat-draft-",
        "'prepza-chat-draft-changed'",
        "getChatDraft(conversationId)",
        "setChatDraft(conversationId, value)",
        "buildChatReactionState(msgs)",
        "chatReplyId(message)",
        "MediaRecorder",
        "stream.getTracks().forEach(track => track.stop())",
        "voiceTimerRef.current",
        "setRecordingSeconds(0)",
        "maxAttachmentSizeBytes",
    ):
        assert contract in detail, f"missing ChatDetail state/media contract: {contract}"


def test_chat_detail_preserves_navigation_and_app_shell_loading_components() -> None:
    detail = _detail_source()
    for contract in (
        "setScreen('chats')",
        "setScreen('chat-options')",
        "setScreen('student-profile')",
        "DelayedScreenSkeleton",
        "SkeletonChatDetail",
        "getFileExtension",
        "allowedUploadExtensions",
    ):
        assert contract in detail, f"missing ChatDetail composition contract: {contract}"
    assert "DelayedScreenSkeleton={DelayedScreenSkeleton}" in APP
    assert "SkeletonChatDetail={SkeletonChatDetail}" in APP
    assert "allowedUploadExtensions={ALLOWED_UPLOAD_EXTENSIONS}" in APP
    assert "maxAttachmentSizeBytes={MAX_CHAT_ATTACHMENT_SIZE_BYTES}" in APP
    assert "getChatDraft } from './screens/chat/ChatDetailScreen'" in APP
