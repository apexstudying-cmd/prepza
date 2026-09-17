from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "e2ee_chat_routes.py"
FRONTEND = Path(__file__).resolve().parents[1] / "frontend/src/crypto/e2eeFetchBridge.ts"


def patch_once(path: Path, old: str, new: str, label: str) -> bool:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return False
    if old not in text:
        raise SystemExit(f"Refusing unsafe {label} patch: expected block not found in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return True


backend_old = '''        provisioner = active_provisioner(conversation.id, expected_epoch)\n        if provisioner is None or user_id != provisioner:\n            return jsonify({"error": "Only the elected group key provisioner may publish the current epoch key", "provisioner_user_id": provisioner, "key_epoch": expected_epoch}), 403\n'''
backend_new = '''        # Any active member may provision an epoch. The key is generated on the\n        # member's device and wrapped separately for every active member, so the\n        # server never receives plaintext group key material. Allowing any active\n        # member also makes recovery from a missing elected-device session safe.\n        provisioner = user_id if participant_for(conversation.id, user_id) else None\n        if provisioner is None:\n            return jsonify({"error": "Only active group members may publish the current epoch key", "key_epoch": expected_epoch}), 403\n'''

frontend_old = '''  if (!activeMembers.length || !activeMembers.includes(currentUserId)) throw new Error('Current member is not active')\n  if (activeMembers[0] !== currentUserId) throw new Error('Waiting for the elected group key provisioner')\n\n  const rotationKey = `${conversationId}:${envelopeState.key_epoch}`\n'''
frontend_new = '''  if (!activeMembers.length || !activeMembers.includes(currentUserId)) throw new Error('Current member is not active')\n\n  const rotationKey = `${conversationId}:${envelopeState.key_epoch}`\n'''

changed_backend = patch_once(BACKEND, backend_old, backend_new, "group key provisioner")
changed_frontend = patch_once(FRONTEND, frontend_old, frontend_new, "group key provisioner client")
print(f"group key provisioner patch: backend={changed_backend} frontend={changed_frontend}")
