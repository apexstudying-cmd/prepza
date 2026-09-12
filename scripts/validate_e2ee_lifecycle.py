"""Static lifecycle checks for Prepza group-chat E2EE.

These checks complement validate_e2ee_security.py. They do not prove the
cryptography or replace multi-browser integration tests; they protect the
membership/epoch lifecycle from accidental regressions.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(path: str, *needles: str) -> None:
    source = (ROOT / path).read_text(encoding="utf-8")
    missing = [needle for needle in needles if needle not in source]
    if missing:
        raise AssertionError(f"{path}: missing lifecycle invariant(s): {missing}")


def main() -> None:
    require(
        "prepza_control.py",
        "ConversationParticipant",
        "left_at",
        "SET key_epoch = key_epoch + 1",
        "Message",
        "e2ee_key_epoch",
        "after_insert",
    )

    require(
        "e2ee_chat_routes.py",
        'SET e2ee_mode = \'group_v1\', key_epoch = 1',
        "active_provisioner(conversation.id, expected_epoch)",
        "locked_epoch != expected_epoch",
        "recipient_user_id",
        "key_epoch",
    )

    require(
        "frontend/src/crypto/e2eeFetchBridge.ts",
        "provisionCurrentEpochIfElected",
        "activeMembers[0] !== currentUserId",
        "provisionRotatedGroupKey",
        "GROUP_LEAVE_RE",
        "Encrypted attachment encryption is not ready on this device",
        "Secure attachment encryption metadata is unavailable",
    )

    require(
        "frontend/src/crypto/newGroupE2EECreationGuard.ts",
        "created.reused !== false",
        "state?.e2ee_mode !== 'group_v1'",
        "state.envelopes.length === 0",
        "Secure group setup is incomplete",
    )

    require(
        "frontend/src/main.tsx",
        "installNewGroupE2EECreationGuard()",
    )

    require(
        "frontend/src/crypto/groupProvisioning.ts",
        "provisionInitialGroupKey",
        "provisionRotatedGroupKey",
        "keyEpoch < 1",
        "keyEpoch < 2",
        "creatorUserId",
    )

    require(
        "frontend/src/crypto/groupStore.ts",
        "keyEpoch",
        "conversationId",
    )

    require(
        "e2ee_ada_routes.py",
        "key_epoch != current_key_epoch",
        'data.get("context_scope") != "selected_document_pages"',
        'data.get("explicit_user_context") is not True',
        "document.user_id != user_id",
    )

    # The student-facing chat must use the normal message/attachment routes;
    # the fetch bridge is the encryption boundary around those calls.
    require(
        "frontend/src/App.tsx",
        "function ChatDetailScreen",
        "/chats/${conversationId}/messages",
        "/chats/${conversationId}/attachments",
        "setScreen('chat-options')",
    )

    print("E2EE lifecycle regression checks passed.")


if __name__ == "__main__":
    main()
