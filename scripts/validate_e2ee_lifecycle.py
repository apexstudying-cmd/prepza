"""Static lifecycle checks for Prepza group/direct-chat E2EE."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(path: str, *needles: str) -> None:
    source = (ROOT / path).read_text(encoding="utf-8")
    missing = [needle for needle in needles if needle not in source]
    if missing:
        raise AssertionError(f"{path}: missing lifecycle invariant(s): {missing}")


def main() -> None:
    require(
        "prepza_control.py", "ConversationParticipant", "left_at", "before_insert",
        "_rotate_group_epoch_on_join", "existing_member", "SET key_epoch = key_epoch + 1",
        "Message", "e2ee_key_epoch", "after_insert",
    )
    require(
        "e2ee_chat_routes.py", "SET e2ee_mode = 'group_v1', key_epoch = 1",
        "active_provisioner(conversation.id, expected_epoch)", "locked_epoch != expected_epoch",
        "recipient_user_id", "key_epoch", "IDENTITY_KEY_REPLACEMENT_REQUIRED",
        '@app.get("/keys/<int:user_id>")',
    )
    require(
        "migrations/fix_group_e2ee_default_state.sql",
        "NEW.e2ee_mode := 'legacy'", "NEW.key_epoch := 0", "trg_prepza_default_new_group_e2ee",
    )
    require(
        "frontend/src/crypto/e2eeFetchBridge.ts", "provisionCurrentEpochIfElected",
        "activeMembers[0] !== currentUserId", "provisionRotatedGroupKey", "GROUP_LEAVE_RE",
        "Secure attachment encryption is not ready on this device",
        "Secure attachment encryption metadata is unavailable",
    )
    require(
        "frontend/src/crypto/newGroupE2EECreationGuard.ts", "created.reused !== false",
        "state?.e2ee_mode !== 'group_v1'", "state.envelopes.length === 0", "Secure group setup is incomplete",
    )
    require(
        "frontend/src/main.tsx",
        "installNewGroupE2EECreationGuard",
        "installSafely('new group E2EE guard', installNewGroupE2EECreationGuard)",
    )
    require(
        "frontend/src/crypto/groupProvisioning.ts", "provisionInitialGroupKey",
        "provisionRotatedGroupKey", "keyEpoch < 1", "keyEpoch < 2", "creatorUserId",
    )
    require("frontend/src/crypto/groupStore.ts", "keyEpoch", "conversationId")
    require(
        "docs/e2ee-multidevice-architecture.md",
        "single-device E2EE release boundary", "user_device", "recipient_device",
        "Never overwrite a device key in place", "must not silently replace",
    )
    require(
        "e2ee_ada_routes.py", "key_epoch != current_key_epoch",
        'context_scope not in {"selected_document_pages", "selected_chat_document"}',
        'data.get("explicit_user_context") is not True', "document.user_id != user_id",
        "attachment_id", "message_attachment", "conversation_id", "status = 'ready'",
    )
    require(
        "frontend/src/crypto/directChatE2EE.ts",
        "DIRECT_ATTACHMENT_KEY_EPOCH = 1", "conversation_id: conversationId",
        "encryptGroupBytes(pendingUpload.key, plaintext, pendingUpload.conversationId, DIRECT_ATTACHMENT_KEY_EPOCH)",
        "decryptGroupBytes(key, encryptedBytes, metadata.file_nonce, conversationId, DIRECT_ATTACHMENT_KEY_EPOCH)",
        "PENDING_ATTACHMENT_TTL_MS", "pruneAttachmentState", "expiresAt",
    )
    require(
        "frontend/src/crypto/e2eeChatApi.ts",
        "fetchUserPublicKey", "`/keys/${userId}`", "Peer encryption key is not available yet",
    )
    require(
        "frontend/src/App.tsx", "function ChatDetailScreen",
        "/chats/${conversationId}/messages", "/chats/${conversationId}/attachments", "setScreen('chat-options')",
    )
    print("E2EE lifecycle regression checks passed.")


if __name__ == "__main__":
    main()
