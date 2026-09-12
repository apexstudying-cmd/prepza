// Prepza group-chat E2EE primitives (Phase 1)
//
// A group has one random 256-bit AES-GCM conversation key on the client.
// That key is wrapped separately for every member using static ECDH
// (the same P-256 identity keys used by 1:1 chat). The server stores only
// the wrapped copies and never receives the plaintext group key.
//
// IMPORTANT: this module does not claim forward secrecy. Membership changes
// must trigger a fresh group key before this is production-complete.

const HKDF_INFO = 'prepza-group-chat-v1'
const GCM_IV_BYTES = 12

function b64(buf: ArrayBuffer | Uint8Array): string {
  const bytes = buf instanceof Uint8Array ? buf : new Uint8Array(buf)
  let s = ''
  for (const byte of bytes) s += String.fromCharCode(byte)
  return btoa(s)
}

function unb64(value: string): Uint8Array {
  const binary = atob(value)
  const out = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i)
  return out
}

async function deriveWrapKey(
  myPrivateKey: CryptoKey,
  peerPublicKey: CryptoKey,
  conversationId: number,
  userId: number,
  peerUserId: number,
): Promise<CryptoKey> {
  const sharedBits = await window.crypto.subtle.deriveBits(
    { name: 'ECDH', public: peerPublicKey } as EcdhKeyDeriveParams,
    myPrivateKey,
    256,
  )
  const base = await window.crypto.subtle.importKey('raw', sharedBits, 'HKDF', false, ['deriveKey'])
  const encoder = new TextEncoder()
  const ids = [userId, peerUserId].sort((a, b) => a - b).join(':')
  return window.crypto.subtle.deriveKey(
    {
      name: 'HKDF',
      hash: 'SHA-256',
      salt: encoder.encode(`${conversationId}:${ids}`) as BufferSource,
      info: encoder.encode(HKDF_INFO) as BufferSource,
    },
    base,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt', 'decrypt'],
  )
}

export interface GroupKeyEnvelope {
  conversationId: number
  recipientUserId: number
  senderUserId: number
  key_epoch?: number
  nonce: string
  ciphertext: string
  version: 1
}

export async function createGroupConversationKey(): Promise<CryptoKey> {
  return window.crypto.subtle.generateKey(
    { name: 'AES-GCM', length: 256 },
    true,
    ['encrypt', 'decrypt'],
  ) as Promise<CryptoKey>
}

export async function wrapGroupKeyForMember(
  groupKey: CryptoKey,
  myPrivateKey: CryptoKey,
  recipientPublicKey: CryptoKey,
  conversationId: number,
  senderUserId: number,
  recipientUserId: number,
  keyEpoch?: number,
): Promise<GroupKeyEnvelope> {
  const wrapKey = await deriveWrapKey(myPrivateKey, recipientPublicKey, conversationId, senderUserId, recipientUserId)
  const rawGroupKey = await window.crypto.subtle.exportKey('raw', groupKey)
  const nonce = window.crypto.getRandomValues(new Uint8Array(GCM_IV_BYTES))
  const ciphertext = await window.crypto.subtle.encrypt(
    { name: 'AES-GCM', iv: nonce as BufferSource },
    wrapKey,
    rawGroupKey,
  )
  return {
    conversationId,
    recipientUserId,
    senderUserId,
    key_epoch: keyEpoch,
    nonce: b64(nonce),
    ciphertext: b64(ciphertext),
    version: 1,
  }
}

export async function unwrapGroupKey(
  envelope: GroupKeyEnvelope,
  myPrivateKey: CryptoKey,
  senderPublicKey: CryptoKey,
): Promise<CryptoKey> {
  const wrapKey = await deriveWrapKey(
    myPrivateKey,
    senderPublicKey,
    envelope.conversationId,
    envelope.recipientUserId,
    envelope.senderUserId,
  )
  const raw = await window.crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: unb64(envelope.nonce) as BufferSource },
    wrapKey,
    unb64(envelope.ciphertext) as BufferSource,
  )
  return window.crypto.subtle.importKey('raw', raw, { name: 'AES-GCM' }, false, ['encrypt', 'decrypt'])
}

export async function encryptGroupMessage(groupKey: CryptoKey, plaintext: string) {
  const nonce = window.crypto.getRandomValues(new Uint8Array(GCM_IV_BYTES))
  const ciphertext = await window.crypto.subtle.encrypt(
    { name: 'AES-GCM', iv: nonce as BufferSource },
    groupKey,
    new TextEncoder().encode(plaintext),
  )
  return { body: b64(ciphertext), nonce: b64(nonce) }
}

export async function decryptGroupMessage(groupKey: CryptoKey, body: string, nonce: string) {
  const plaintext = await window.crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: unb64(nonce) as BufferSource },
    groupKey,
    unb64(body) as BufferSource,
  )
  return new TextDecoder().decode(plaintext)
}

export async function encryptGroupBytes(groupKey: CryptoKey, bytes: ArrayBuffer | Uint8Array) {
  const nonce = window.crypto.getRandomValues(new Uint8Array(GCM_IV_BYTES))
  const ciphertext = await window.crypto.subtle.encrypt(
    { name: 'AES-GCM', iv: nonce as BufferSource },
    groupKey,
    bytes instanceof Uint8Array ? bytes as BufferSource : bytes,
  )
  return { ciphertext, nonce: b64(nonce) }
}

export async function decryptGroupBytes(groupKey: CryptoKey, ciphertext: ArrayBuffer | Uint8Array, nonce: string) {
  return window.crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: unb64(nonce) as BufferSource },
    groupKey,
    ciphertext instanceof Uint8Array ? ciphertext as BufferSource : ciphertext,
  )
}
