from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "frontend" / "src" / "App.tsx"

REQUIRED_SCREENS = {
    "home",
    "explore",
    "chats",
    "chat-detail",
    "opportunities",
    "opportunity-detail",
    "library",
    "document-study",
    "document-reader",
    "ai-tutor",
    "summary",
    "flashcards",
    "quiz",
    "mind-map",
    "podcast-player",
    "podcast-library",
    "profile",
    "student-profile",
    "settings",
    "notifications",
    "subscription",
    "payment-history",
    "study-activity",
}

REQUIRED_FRONTEND_CONTRACTS = {
    "frontend/src/screens/explore/ExploreScreen.tsx": (
        "/students",
    ),
    "frontend/src/crypto/WhatsAppChatExperience.tsx": (
        "api<{ chats: ChatSummary[] }>('/chats')",
        "`/chats/${chat.id}`",
    ),
    "frontend/src/screens/chat/ChatDetailScreen.tsx": (
        "`/chats/${conversationId}`",
        "`/chats/${conversationId}/messages`",
    ),
}

REQUIRED_BACKEND_ROUTE_ANCHORS = [
    '@app.get("/students")',
    '@app.get("/message-requests")',
    '@app.post("/chats/<int:conversation_id>/accept-request")',
    '@app.post("/chats/<int:conversation_id>/decline-request")',
]

if not APP.exists():
    raise SystemExit("STUDENT_SCREEN_CONTRACT_FAILED: App.tsx missing")

frontend = APP.read_text(encoding="utf-8")
backend_sources = [
    p.read_text(encoding="utf-8")
    for p in ROOT.rglob("*.py")
    if ".git" not in p.parts and "__pycache__" not in p.parts
]
backend = "\n".join(backend_sources)

case_screens = set(re.findall(r"case ['\"]([^'\"]+)['\"]\s*:", frontend))
missing_screens = sorted(REQUIRED_SCREENS - case_screens)
if missing_screens:
    raise SystemExit(
        "STUDENT_SCREEN_CONTRACT_FAILED: missing screen cases: "
        + ", ".join(missing_screens)
    )

missing_frontend = []
for relative_path, markers in REQUIRED_FRONTEND_CONTRACTS.items():
    source_path = ROOT / relative_path
    if not source_path.exists():
        missing_frontend.append(f"{relative_path} (module missing)")
        continue
    source = source_path.read_text(encoding="utf-8")
    missing_frontend.extend(
        f"{relative_path}: {marker}"
        for marker in markers
        if marker not in source
    )
if missing_frontend:
    raise SystemExit(
        "STUDENT_SCREEN_CONTRACT_FAILED: frontend missing active module contract(s): "
        + "; ".join(missing_frontend)
    )

missing_backend = [
    anchor for anchor in REQUIRED_BACKEND_ROUTE_ANCHORS
    if anchor not in backend
]
if missing_backend:
    raise SystemExit(
        "STUDENT_SCREEN_CONTRACT_FAILED: backend missing critical route(s): "
        + ", ".join(missing_backend)
    )

# The message-request lifecycle must not accidentally expose a pending request
# to the recipient through the ordinary conversation loader.
required_security_anchors = [
    'conversation.status == "pending"',
    'conversation.created_by != user_id',
    'Conversation.status == "accepted"',
]
for anchor in required_security_anchors:
    if anchor not in backend:
        raise SystemExit(
            f"STUDENT_SCREEN_CONTRACT_FAILED: missing message-request security anchor: {anchor}"
        )

print("STUDENT_SCREEN_CONTRACT_PASSED")
print(f" - required student screens: {len(REQUIRED_SCREENS)}")
print(" - Explore student directory and active chat list/detail contracts: present")
print(" - Message-request backend routes and pending recipient isolation: present")
