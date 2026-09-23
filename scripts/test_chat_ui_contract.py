"""Static regression checks for the production chat UX contract.

These checks intentionally avoid rendering React in CI. They verify that the
live chat surface still contains the user-facing capabilities that Chunk 2
promises, while the runtime tests cover the backend/realtime behavior.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHAT = ROOT / "frontend" / "src" / "crypto" / "WhatsAppChatExperience.tsx"
MAIN = ROOT / "frontend" / "src" / "main.tsx"
DRAFTS = ROOT / "frontend" / "src" / "crypto" / "chatDraftPersistence.ts"


def test_chat_surface_contains_whatsapp_core_interactions():
    text = CHAT.read_text(encoding="utf-8")
    required = {
        "conversation search": "Search conversations",
        "group creation": "New study group",
        "reply": "Reply",
        "reactions": "React",
        "attachments": "Attach document or image",
        "typing": "typing…",
        "read receipts": "read_by_count",
        "presence": "onlineUsers",
        "E2EE indicator": "End-to-end encrypted",
        "Ada entry point": "@Ada",
        "load earlier": "Load earlier messages",
        "mobile layout": "@media(max-width:760px)",
    }
    missing = [name for name, marker in required.items() if marker not in text]
    assert not missing, f"Chat UX contract missing: {', '.join(missing)}"


def test_chat_startup_installs_required_enhancers():
    text = MAIN.read_text(encoding="utf-8")
    required = {
        "realtime": "installChatRealtime",
        "swipe reply": "installChatSwipeReply",
        "UI polish": "installChatUiPolish",
        "draft persistence": "installChatDraftPersistence",
        "in-chat Ada": "installInChatAdaObserver",
        "document study": "installChatStudyDocumentObserver",
    }
    missing = [name for name, marker in required.items() if marker not in text]
    assert not missing, f"Chat startup enhancers missing: {', '.join(missing)}"


def test_per_conversation_draft_persistence_is_wired():
    assert DRAFTS.exists(), "Per-conversation draft persistence module is missing"
    text = DRAFTS.read_text(encoding="utf-8")
    for marker in ("prepza-chat-draft:", "localStorage", "activeConversationId"):
        assert marker in text, f"Draft persistence marker missing: {marker}"
