"""Static regression checks for Prepza group-chat E2EE boundaries.

These checks intentionally do not claim to prove cryptographic correctness.
They guard the server-side invariants that are easy to accidentally weaken
when chat routes are edited: group plaintext rejection, deterministic key
provisioning, current-epoch enforcement, and scoped Ada context.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(path: str, *needles: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    missing = [needle for needle in needles if needle not in text]
    if missing:
        raise AssertionError(f"{path}: missing required security invariant(s): {missing}")


def forbid(path: str, *needles: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    present = [needle for needle in needles if needle in text]
    if present:
        raise AssertionError(f"{path}: forbidden pattern(s) found: {present}")


def main() -> None:
    require(
        "e2ee_chat_routes.py",
        "_reject_plaintext_group_message_write",
        'mode != "group_v1"',
        'Plaintext group messages are disabled; encrypt on the client first',
        "active_provisioner(conversation.id, expected_epoch)",
        "Only the elected group key provisioner may publish the current epoch key",
        "epoch != expected_epoch",
        "Envelope recipient is not an active member",
    )

    require(
        "e2ee_ada_routes.py",
        'data.get("context_scope") != "selected_document_pages"',
        'data.get("explicit_user_context") is not True',
        "key_epoch != current_key_epoch",
        "document_id",
        "selected_text",
        "prompt",
    )

    require(
        "frontend/src/crypto/group.ts",
        "deriveWrapKey",
        "AES-GCM",
        "ECDH",
        "HKDF",
        "encryptGroupMessage",
        "decryptGroupMessage",
    )

    require(
        "frontend/src/crypto/groupSession.ts",
        "importPeerPublicKey",
        "openGroupE2EESession",
    )

    # The server must never gain a helper that accepts a plaintext group key.
    forbid(
        "e2ee_chat_routes.py",
        "group_key",  # server route source must stay key-material opaque
    )

    print("E2EE security regression checks passed.")


if __name__ == "__main__":
    main()
