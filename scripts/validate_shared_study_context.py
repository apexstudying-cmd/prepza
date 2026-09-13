"""Static validation for the shared-study / scoped-Ada client boundary."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(path: str, *needles: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    missing = [needle for needle in needles if needle not in text]
    if missing:
        raise SystemExit(f"{path}: missing required invariants: {missing}")


require(
    "frontend/src/crypto/studyAdaContext.ts",
    "MAX_PAGE_SPAN = 50",
    "keyEpoch < 1",
    "Document and chat attachment context cannot be combined.",
    "explicit: true",
    "explicit_user_context: true",
)
require(
    "frontend/src/crypto/studyAdaApi.ts",
    "navigator.onLine === false",
    "30_000",
    "value.key_epoch !== context.keyEpoch",
    "value.context_scope !== context.contextScope",
)
require(
    "frontend/src/crypto/chatStudyDocumentReader.tsx",
    "selected_chat_document",
    "attachmentId",
    "The file is decrypted locally.",
)
require(
    "frontend/src/crypto/e2eeFetchBridge.ts",
    "decryptGroupBytes(fileKey, encryptedBytes, metadata.file_nonce)",
    "URL.createObjectURL",
    "hydrateEncryptedAttachment",
)
require(
    "e2ee_ada_routes.py",
    "explicit_user_context",
    "context_scope",
    "message_attachment",
    "conversation_id = :conversation_id",
)

print("Shared-study context validation passed.")
