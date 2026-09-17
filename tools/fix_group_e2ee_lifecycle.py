from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 1) A group must never silently fall back to plaintext messaging. Existing
# legacy groups remain readable, but their new writes wait for E2EE setup.
route = ROOT / 'e2ee_chat_routes.py'
s = route.read_text(encoding='utf-8')
old = '''            conversation_id = int(match.group(1))\n            mode, _ = e2ee_state(conversation_id)\n            if mode != "group_v1":\n                return None\n'''
new = '''            conversation_id = int(match.group(1))\n            conversation = Conversation.query.get(conversation_id)\n            if not conversation or not getattr(conversation, "is_group", False):\n                return None\n            mode, _ = e2ee_state(conversation_id)\n'''
if new not in s:
    if old not in s:
        raise SystemExit('group lifecycle: plaintext guard anchor missing')
    s = s.replace(old, new, 1)

# Any active member may complete the initial enablement once every member has
# a registered public identity key. The actual group key is still generated
# and wrapped on a member device; the server receives envelopes only.
old = '''        if conversation.created_by != user_id:\n            return jsonify({"error": "Only the group creator can enable E2EE"}), 403\n'''
new = '''        if not participant_for(conversation.id, user_id):\n            return jsonify({"error": "Only an active group member can enable E2EE"}), 403\n'''
if new not in s:
    if old not in s:
        raise SystemExit('group lifecycle: creator-only enable anchor missing')
    s = s.replace(old, new, 1)
route.write_text(s, encoding='utf-8')

# 2) Allow the same secure device-side provisioning primitive to create epoch 1
# when the creator's device is not the member completing setup.
prov = ROOT / 'frontend/src/crypto/groupProvisioning.ts'
s = prov.read_text(encoding='utf-8')
old = "  if (!Number.isInteger(keyEpoch) || keyEpoch < 2) throw new Error('Invalid rotated group key epoch.')"
new = "  if (!Number.isInteger(keyEpoch) || keyEpoch < 1) throw new Error('Invalid group key epoch.')"
if new not in s:
    if old not in s:
        raise SystemExit('group lifecycle: rotated epoch validation anchor missing')
    s = s.replace(old, new, 1)
prov.write_text(s, encoding='utf-8')

# 3) Group detection now drives provisioning rather than falling through to
# plaintext. If the current member has all public keys available, that member
# can safely finish enablement and upload only encrypted envelopes.
bridge = ROOT / 'frontend/src/crypto/e2eeFetchBridge.ts'
s = bridge.read_text(encoding='utf-8')
old = '''async function groupIsE2EE(conversationId: number): Promise<boolean> {\n  const cached = groupModeCache.get(conversationId)\n  if (cached !== undefined) return cached\n  const response = await window.fetch(`/chats/${conversationId}/key-envelopes`, { credentials: 'include' })\n  if (!response.ok) return false\n  const body = await response.clone().json().catch(() => null)\n  const enabled = body?.e2ee_mode === 'group_v1'\n  groupModeCache.set(conversationId, enabled)\n  return enabled\n}\n'''
new = '''async function groupIsE2EE(conversationId: number): Promise<boolean> {\n  const cached = groupModeCache.get(conversationId)\n  if (cached !== undefined) return cached\n  const detail = await fetchGroupDetail(conversationId).catch(() => null)\n  if (!detail?.is_group) { groupModeCache.set(conversationId, false); return false }\n  const response = await window.fetch(`/chats/${conversationId}/key-envelopes`, { credentials: 'include' })\n  if (!response.ok) return false\n  const body = await response.clone().json().catch(() => null)\n  if (body?.e2ee_mode === 'group_v1') { groupModeCache.set(conversationId, true); return true }\n\n  // Legacy group: attempt secure migration now. This never sends plaintext.\n  // If another member has not registered a public key yet, leave the group in\n  // a blocked state until that member opens Prepza and completes secure setup.\n  try {\n    const csrfToken = currentCsrfToken\n    await ensureIdentityKeyRegistered(csrfToken)\n    const enable = await window.fetch(`/chats/${conversationId}${GROUP_ENABLE_SUFFIX}`, {\n      method: 'POST', credentials: 'include',\n      headers: { 'Content-Type': 'application/json', ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}) },\n      body: '{}',\n    })\n    const enableBody = await enable.json().catch(() => null)\n    if (!enable.ok) return false\n    const epoch = Number(enableBody?.key_epoch)\n    if (!Number.isInteger(epoch) || epoch < 1 || !currentUserId) return false\n    const members = await Promise.all((detail.participants || []).map(async (p: any) => ({\n      userId: Number(p.user_id),\n      publicKey: await fetchUserPublicKey(Number(p.user_id)),\n    })))\n    await provisionRotatedGroupKey(conversationId, epoch, currentUserId, members, async (id, envelopes) => uploadGroupKeyEnvelopes(id, csrfToken, envelopes))\n    groupModeCache.set(conversationId, true)\n    return true\n  } catch {\n    return false\n  }\n}\n'''
if new not in s:
    if old not in s:
        raise SystemExit('group lifecycle: groupIsE2EE anchor missing')
    s = s.replace(old, new, 1)
bridge.write_text(s, encoding='utf-8')
print('GROUP_E2EE_LIFECYCLE_FIXED')
