"""Static regression checks for Prepza chat E2EE boundaries."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(path: str, *needles: str) -> None:
    source = (ROOT / path).read_text(encoding="utf-8")
    missing = [needle for needle in needles if needle not in source]
    if missing:
        raise AssertionError(f"{path}: missing required security invariant(s): {missing}")


def forbid(path: str, *needles: str) -> None:
    source = (ROOT / path).read_text(encoding="utf-8")
    present = [needle for needle in needles if needle in source]
    if present:
        raise AssertionError(f"{path}: forbidden pattern(s) found: {present}")


def main() -> None:
    require(
        "e2ee_chat_routes.py",
        "def _reject_plaintext_group_message_write():",
        'if mode != "group_v1":',
        'Plaintext group messages are disabled; encrypt on the client first',
        "provisioner = active_provisioner(conversation.id, expected_epoch)",
        "Only the elected group key provisioner may publish the current epoch key",
        "epoch != expected_epoch",
        "Envelope recipient is not an active member",
    )

    require(
        "e2ee_ada_routes.py",
        "_reject_plaintext_direct_message_write",
        'state != "direct_v1"',
        'Plaintext direct messages are disabled; encrypt on the client first',
        'e2ee_mode not in {"group_v1", "direct_v1"}',
        'context_scope not in {"selected_document_pages", "selected_chat_document"}',
        'message_attachment',
        "message_id IS NOT NULL",
        "status = 'ready'",
        "if key_epoch != current_key_epoch:",
        "selected_text = clean_text(data.get(\"selected_text\")",
        "prompt = clean_text(data.get(\"prompt\")",
        "document.user_id != user_id",
        'getattr(document, "is_removed", False)',
    )

    require(
        "frontend/src/crypto/studyAdaFetchGuard.ts",
        "STUDY_ADA_RE",
        "selected_document_pages",
        "selected_chat_document",
        "attachment_id",
        "explicit_user_context !== true",
        "MAX_SELECTED_TEXT = 20_000",
        "MAX_PROMPT = 4_000",
        "MAX_PAGE_SPAN = 50",
        "const safePayload = {",
        "selected_text: payload.selected_text",
        "prompt: payload.prompt",
    )

    require(
        "frontend/src/crypto/studyAdaContext.ts",
        "attachmentId?: number",
        "selected_chat_document",
        "contextScope",
        "toAdaRequestBody",
    )

    require(
        "frontend/src/crypto/chatStudyDocumentReader.tsx",
        "installChatStudyDocumentObserver",
        "activeDocuments",
        "const seen = new Set<number>()",
        "documents.length > 1",
        "selected_chat_document",
        "The file is decrypted locally.",
    )

    require(
        "frontend/src/crypto/group.ts",
        "async function deriveWrapKey(",
        "name: 'AES-GCM'",
        "name: 'ECDH'",
        "name: 'HKDF'",
        "export async function encryptGroupMessage(",
        "export async function decryptGroupMessage(",
    )

    require(
        "frontend/src/crypto/groupProvisioning.ts",
        "function validateMemberTargets(",
        "keyEpoch < 1",
        "keyEpoch < 2",
        "Missing public key for member",
    )

    require(
        "frontend/src/crypto/e2eeFetchBridge.ts",
        "encryptGroupBytes",
        "decryptGroupBytes",
        "ENCRYPTED_ATTACHMENT_MARKER",
        "localSearchGroupMessages",
        "Encrypted attachment download failed",
    )

    require(
        "frontend/src/crypto/directChatE2EE.ts",
        "deriveConversationKey",
        "encryptMessageBody",
        "decryptMessageBody",
        "localSearchDirectMessages",
        "encryptGroupBytes",
        "decryptGroupBytes",
        "ENCRYPTED_ATTACHMENT_MARKER",
    )

    require(
        "frontend/src/crypto/directInChatAdaEnhancer.tsx",
        "installDirectInChatAdaObserver",
        "createAdaStudyContext",
        "askAdaAboutSelectedStudyContext",
        "Only the study context you choose is sent to Ada.",
    )

    forbid(
        "e2ee_chat_routes.py",
        '"group_key"',
        "payload.get(\"group_key\")",
        "data.get(\"group_key\")",
    )

    print("E2EE security regression checks passed.")


if __name__ == "__main__":
    main()
