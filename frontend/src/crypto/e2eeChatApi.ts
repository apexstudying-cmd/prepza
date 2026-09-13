import { decryptGroupMessage, encryptGroupMessage, type GroupKeyEnvelope } from './group'
import { openGroupE2EESession, type GroupE2EEState } from './groupSession'
import { exportPublicKeyBase64Url, getOrCreateIdentityKeyPair } from './keys'

let identityReadyPromise: Promise<void> | null = null

async function jsonFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, { credentials: 'include', ...options, headers: { 'Content-Type': 'application/json', ...(options.headers || {}) } })
  let body: any = null
  try { body = await response.json() } catch { /* empty response */ }
  if (!response.ok) throw new Error((body && body.error) || `Request failed (${response.status})`)
  return body as T
}

export type GroupEnvelopeResponse = {
  conversation_id: number
  key_epoch: number
  e2ee_mode: string
  envelopes: GroupKeyEnvelope[]
}

export async function fetchGroupKeyEnvelopes(conversationId: number): Promise<GroupEnvelopeResponse> {
  return jsonFetch<GroupEnvelopeResponse>(`/chats/${conversationId}/key-envelopes`)
}

export async function uploadGroupKeyEnvelopes(conversationId: number, csrfToken: string, envelopes: GroupKeyEnvelope[]): Promise<void> {
  await jsonFetch(`/chats/${conversationId}/key-envelopes`, {
    method: 'POST',
    headers: { 'X-CSRF-Token': csrfToken },
    body: JSON.stringify({ envelopes: envelopes.map(envelope => ({
      conversation_id: envelope.conversationId,
      recipient_user_id: envelope.recipientUserId,
      sender_user_id: envelope.senderUserId,
      key_epoch: envelope.key_epoch,
      version: envelope.version,
      nonce: envelope.nonce,
      ciphertext: envelope.ciphertext,
    })) }),
  })
}

export async function registerUserPublicKey(publicKey: string): Promise<void> {
  await jsonFetch('/keys/register', { method: 'POST', body: JSON.stringify({ public_key: publicKey }) })
}

export async function ensureE2EEIdentityReady(): Promise<void> {
  if (identityReadyPromise) return identityReadyPromise
  identityReadyPromise = (async () => {
    const me = await jsonFetch<{ id: number }>('/me')
    if (!me?.id) throw new Error('Authentication required')
    const { keyPair } = await getOrCreateIdentityKeyPair()
    await registerUserPublicKey(await exportPublicKeyBase64Url(keyPair.publicKey))
  })()
  try { await identityReadyPromise } catch (error) { identityReadyPromise = null; throw error }
}

export async function fetchUserPublicKey(userId: number): Promise<string> {
  const attempts = 4
  let lastError: unknown = null
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const result = await jsonFetch<{ public_key: string }>(`/keys/${userId}`)
      if (result.public_key) return result.public_key
      lastError = new Error('Peer encryption key is not available yet')
    } catch (error) { lastError = error }
    if (attempt < attempts - 1) await new Promise(resolve => window.setTimeout(resolve, 400 * (attempt + 1)))
  }
  throw lastError instanceof Error ? lastError : new Error('Secure conversation is temporarily unavailable')
}

export async function openGroupSession(conversationId: number): Promise<GroupE2EEState> {
  return openGroupE2EESession(conversationId, fetchGroupKeyEnvelopes, fetchUserPublicKey)
}

export async function encryptGroupText(key: CryptoKey, plaintext: string, conversationId: number, keyEpoch: number) {
  return encryptGroupMessage(key, plaintext, conversationId, keyEpoch)
}

export async function decryptGroupText(key: CryptoKey, body: string, nonce: string, conversationId: number, keyEpoch: number) {
  return decryptGroupMessage(key, body, nonce, conversationId, keyEpoch)
}
