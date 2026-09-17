from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / "frontend" / "src" / "crypto" / "e2eeFetchBridge.ts"
OLD = '''async function groupIsE2EE(conversationId: number): Promise<boolean> {
  const cached = groupModeCache.get(conversationId)
  if (cached !== undefined) return cached
  const response = await window.fetch(`/chats/${conversationId}/key-envelopes`, { credentials: 'include' })
  if (!response.ok) return false
  const body = await response.clone().json().catch(() => null)
  const enabled = body?.e2ee_mode === 'group_v1'
  groupModeCache.set(conversationId, enabled)
  return enabled
}
'''
NEW = '''async function groupIsE2EE(conversationId: number): Promise<boolean> {
  const cached = groupModeCache.get(conversationId)
  if (cached !== undefined) return cached

  // key-envelopes is a group-only endpoint. Determine the conversation type
  // first so direct chats never generate a misleading 400 request.
  const detail = await fetchGroupDetail(conversationId).catch(() => null)
  if (!detail?.is_group) {
    groupModeCache.set(conversationId, false)
    return false
  }

  const response = await window.fetch(`/chats/${conversationId}/key-envelopes`, { credentials: 'include' })
  if (!response.ok) return false
  const body = await response.clone().json().catch(() => null)
  const enabled = body?.e2ee_mode === 'group_v1'
  groupModeCache.set(conversationId, enabled)
  return enabled
}
'''

text = TARGET.read_text(encoding="utf-8")
if NEW in text:
    print("Direct-chat E2EE probe fix already applied")
elif OLD in text:
    TARGET.write_text(text.replace(OLD, NEW), encoding="utf-8")
    print("Applied direct-chat E2EE probe fix")
else:
    raise SystemExit("Expected groupIsE2EE block not found; refusing unsafe patch")
