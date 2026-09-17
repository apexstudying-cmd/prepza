from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

# 1) A group must never silently fall back to plaintext messaging. Existing
# legacy groups remain readable, but their new writes wait for E2EE setup.
route = ROOT / 'e2ee_chat_routes.py'
s = route.read_text(encoding='utf-8')
old = '''            conversation_id = int(match.group(1))
            mode, _ = e2ee_state(conversation_id)
            if mode != "group_v1":
                return None
'''
new = '''            conversation_id = int(match.group(1))
            conversation = Conversation.query.get(conversation_id)
            if not conversation or not getattr(conversation, "is_group", False):
                return None
            mode, _ = e2ee_state(conversation_id)
'''
if new not in s:
    if old in s:
        s = s.replace(old, new, 1)
    elif 'if not conversation or not getattr(conversation, "is_group", False):' not in s:
        raise SystemExit('group lifecycle: plaintext guard anchor missing')

old = '''        if conversation.created_by != user_id:
            return jsonify({"error": "Only the group creator can enable E2EE"}), 403
'''
new = '''        if not participant_for(conversation.id, user_id):
            return jsonify({"error": "Only an active group member can enable E2EE"}), 403
'''
if new not in s:
    if old in s:
        s = s.replace(old, new, 1)
    elif 'Only an active group member can enable E2EE' not in s:
        raise SystemExit('group lifecycle: creator-only enable anchor missing')
route.write_text(s, encoding='utf-8')

# 2) Allow epoch 1 for device-side group provisioning.
prov = ROOT / 'frontend/src/crypto/groupProvisioning.ts'
s = prov.read_text(encoding='utf-8')
old = "  if (!Number.isInteger(keyEpoch) || keyEpoch < 2) throw new Error('Invalid rotated group key epoch.')"
new = "  if (!Number.isInteger(keyEpoch) || keyEpoch < 1) throw new Error('Invalid group key epoch.')"
if new not in s and old in s:
    s = s.replace(old, new, 1)
prov.write_text(s, encoding='utf-8')

# 3) Make group detection/provisioning deterministic and idempotent. We replace
# the whole function rather than relying on an earlier patch's exact formatting,
# because multiple build-time repair passes may touch this file in sequence.
bridge = ROOT / 'frontend/src/crypto/e2eeFetchBridge.ts'
s = bridge.read_text(encoding='utf-8')
new_fn = '''async function groupIsE2EE(conversationId: number): Promise<boolean> {
  const cached = groupModeCache.get(conversationId)
  if (cached !== undefined) return cached
  const detail = await fetchGroupDetail(conversationId).catch(() => null)
  if (!detail?.is_group) { groupModeCache.set(conversationId, false); return false }
  const response = await window.fetch(`/chats/${conversationId}/key-envelopes`, { credentials: 'include' })
  if (!response.ok) return false
  const body = await response.clone().json().catch(() => null)
  if (body?.e2ee_mode === 'group_v1') { groupModeCache.set(conversationId, true); return true }

  // Legacy group: attempt secure migration. No plaintext fallback is allowed.
  try {
    const csrfToken = currentCsrfToken
    await ensureIdentityKeyRegistered(csrfToken)
    const enable = await window.fetch(`/chats/${conversationId}${GROUP_ENABLE_SUFFIX}`, {
      method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}) },
      body: '{}',
    })
    const enableBody = await enable.json().catch(() => null)
    if (!enable.ok) return false
    const epoch = Number(enableBody?.key_epoch)
    if (!Number.isInteger(epoch) || epoch < 1 || !currentUserId) return false
    const members = await Promise.all((detail.participants || []).map(async (p: any) => ({
      userId: Number(p.user_id),
      publicKey: await fetchUserPublicKey(Number(p.user_id)),
    })))
    await provisionRotatedGroupKey(conversationId, epoch, currentUserId, members, async (id, envelopes) => uploadGroupKeyEnvelopes(id, csrfToken, envelopes))
    groupModeCache.set(conversationId, true)
    return true
  } catch {
    return false
  }
}
'''
pattern = r'async function groupIsE2EE\(conversationId: number\): Promise<boolean> \{.*?\n\}\n\n(?=async function decryptMessageWithEpoch)'
if re.search(pattern, s, flags=re.S):
    s = re.sub(pattern, new_fn + '\n', s, count=1, flags=re.S)
else:
    raise SystemExit('group lifecycle: groupIsE2EE function not found')
bridge.write_text(s, encoding='utf-8')
print('GROUP_E2EE_LIFECYCLE_FIXED')
