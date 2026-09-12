"""Static regression checks for Prepza group-chat E2EE boundaries.

These checks intentionally do not claim to prove cryptographic correctness.
They guard server-side invariants that are easy to accidentally weaken when
chat routes are edited: plaintext rejection, deterministic key provisioning,
current-epoch enforcement, and explicitly scoped Ada context.
"""

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
        'data.get("context_scope") != "selected_document_pages"',
        'data.get("explicit_user_context") is not True',
        "if key_epoch != current_key_epoch:",
        "document_id = int(data.get(\"document_id\"))",
        "selected_text = clean_text(data.get(\"selected_text\")",
        "prompt = clean_text(data.get(\"prompt\")",
    )

    require(
        "frontend/src/crypto/group.ts",
        "async function deriveWrapKey(",
        'name: \'AES-GCM\'',
        'name: \'ECDH\'',
        'name: \'HKDF\'',
        "export async function encryptGroupMessage(",
        "export async function decryptGroupMessage(",
    )

    require(
        "frontend/src/crypto/groupSession.ts",
        "import { getOrCreateIdentityKeyPair, importPeerPublicKey }",
        "export async function openGroupE2EESession(",
    )

    # The server route must not contain an API field/helper that accepts a
    # plaintext group key. Hyphenated prose such as "group-key" is harmless.
    forbid(
        "e2ee_chat_routes.py",
        '"group_key"',
        "payload.get(\"group_key\")",
        "data.get(\"group_key\")",
    )

    print("E2EE security regression checks passed.")


if __name__ == "__main__":
    main()
