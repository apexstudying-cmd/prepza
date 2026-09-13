// Prepza group-chat E2EE primitives.
// Group keys are wrapped per member with ECDH and all ciphertext is bound to
// its conversation/epoch through AES-GCM authenticated additional data.

const HKDF_INFO = 'prepza-group-chat-v1'
const GCM_IV_BYTES = 12
const GROUP_KEY_BYTES = 32

function b64(buf: ArrayBuffer | Uint8Array): string {
  const bytes = buf instanceof Uint8Array ? buf : new Uint8Array(buf)
  let s = ''
  for (const byte of bytes) s += String.fromCharCode(byte)
  return btoa(s)
}

function unb64(value: string): Uint8Array {
  if (typeof value !== 'string' || !value || !/^[A-Za-z0-9+/]*={0,2}$/.test(value) || value.length % 4 === 1) {
    throw new Error('Invalid base64 value.')
  }
  const binary = atob(value)
  const out = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i)
  return out
}

function assertId(value: number, label: string): void {
  if (!Number.isInteger(value) || value <= 0) throw new Error(`Invalid ${label}.`)
}

function assertEpoch(value: number | undefined): asserts value is number {
  if (!Number.isInteger(value) || value < 1) throw new Error('Invalid group key epoch.')
}

function envelopeAad(conversationId: number, senderUserId: number, recipientUserId: number, keyEpoch: number): Uint8Array {
  assertId(conversationId, 'conversation id')
  assertId(senderUserId, 'sender user id')
  assertId(recipientUserId, 'recipient user id')
  assertEpoch(keyEpoch)
  return new TextEncoder().encode(`prepza:group-key-envelope:v1:${conversationId}:${senderUserId}:${recipientUserId}:${keyEpoch}`)
}

function messageAad(conversationId: number, keyEpoch: number, purpose: string): Uint8Array {
  assertId(conversationId, 'conversation id')
  assertEpoch(keyEpoch)
  if (!purpose || purpose.length > 64) throw new Error('Invalid crypto purpose.')
  return new TextEncoder().encode(`prepza:group:${purpose}:v1:${conversationId}:${keyEpoch}`)
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
  assertId(conversationId, 'conversation id')
  assertId(senderUserId, 'sender user id')
  assertId(recipientUserId, 'recipient user id')
  assertEpoch(keyEpoch)
  const wrapKey = await deriveWrapKey(myPrivateKey, recipientPublicKey, conversationId, senderUserId, recipientUserId)
  const rawGroupKey = await window.crypto.subtle.exportKey('raw', groupKey)
  if (rawGroupKey.byteLength !== GROUP_KEY_BYTES) throw new Error('Invalid group conversation key.')
  const nonce = window.crypto.getRandomValues(new Uint8Array(GCM_IV_BYTES))
  const ciphertext = await window.crypto.subtle.encrypt(
    { name: 'AES-GCM', iv: nonce as BufferSource, additionalData: envelopeAad(conversationId, senderUserId, recipientUserId, keyEpoch) as BufferSource },
    wrapKey,
    rawGroupKey,
  )
  return { conversationId, recipientUserId, senderUserId, key_epoch: keyEpoch, nonce: b64(nonce), ciphertext: b64(ciphertext), version: 1 }
}

export async function unwrapGroupKey(
  envelope: GroupKeyEnvelope,
  myPrivateKey: CryptoKey,
  senderPublicKey: CryptoKey,
): Promise<CryptoKey> {
  assertId(envelope.conversationId, 'conversation id')
  assertId(envelope.recipientUserId, 'recipient user id')
  assertId(envelope.senderUserId, 'sender user id')
  assertEpoch(envelope.key_epoch)
  if (envelope.version !== 1) throw new Error('Unsupported group key envelope version.')
  const nonce = unb64(envelope.nonce)
  const ciphertext = unb64(envelope.ciphertext)
  if (nonce.length !== GCM_IV_BYTES || ciphertext.length < GROUP_KEY_BYTES + 16) throw new Error('Malformed group key envelope.')
  const wrapKey = await deriveWrapKey(myPrivateKey, senderPublicKey, envelope.conversationId, envelope.recipientUserId, envelope.senderUserId)
  const raw = await window.crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: nonce as BufferSource, additionalData: envelopeAad(envelope.conversationId, envelope.senderUserId, envelope.recipientUserId, envelope.key_epoch) as BufferSource },
    wrapKey,
    ciphertext as BufferSource,
  )
  if (raw.byteLength !== GROUP_KEY_BYTES) throw new Error('Invalid decrypted group key.')
  return window.crypto.subtle.importKey('raw', raw, { name: 'AES-GCM' }, false, ['encrypt', 'decrypt'])
}

export async function encryptGroupMessage(groupKey: CryptoKey, plaintext: string, conversationId?: number, keyEpoch?: number) {
  const nonce = window.crypto.getRandomValues(new Uint8Array(GCM_IV_BYTES))
  const params: AesGcmParams = { name: 'AES-GCM', iv: nonce as BufferSource }
  if (conversationId !== undefined || keyEpoch !== undefined) {
    if (conversationId === undefined || keyEpoch === undefined) throw new Error('Conversation and epoch are required together.')
    params.additionalData = messageAad(conversationId, keyEpoch, 'message') as BufferSource
  }
  const ciphertext = await window.crypto.subtle.encrypt(params, groupKey, new TextEncoder().encode(plaintext))
  return { body: b64(ciphertext), nonce: b64(nonce) }
}

export async function decryptGroupMessage(groupKey: CryptoKey, body: string, nonce: string, conversationId?: number, keyEpoch?: number) {
  const iv = unb64(nonce)
  if (iv.length !== GCM_IV_BYTES) throw new Error('Invalid message nonce.')
  const params: AesGcmParams = { name: 'AES-GCM', iv: iv as BufferSource }
  if (conversationId !== undefined || keyEpoch !== undefined) {
    if (conversationId === undefined || keyEpoch === undefined) throw new Error('Conversation and epoch are required together.')
    params.additionalData = messageAad(conversationId, keyEpoch, 'message') as BufferSource
  }
  const plaintext = await window.crypto.subtle.decrypt(params, groupKey, unb64(body) as BufferSource)
  return new TextDecoder().decode(plaintext)
}

export async function encryptGroupBytes(groupKey: CryptoKey, bytes: ArrayBuffer | Uint8Array, conversationId?: number, keyEpoch?: number) {
  const nonce = window.crypto.getRandomValues(new Uint8Array(GCM_IV_BYTES))
  const params: AesGcmParams = { name: 'AES-GCM', iv: nonce as BufferSource }
  if (conversationId !== undefined || keyEpoch !== undefined) {
    if (conversationId === undefined || keyEpoch === undefined) throw new Error('Conversation and epoch are required together.')
    params.additionalData = messageAad(conversationId, keyEpoch, 'attachment') as BufferSource
  }
  const input = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes)
  const ciphertext = await window.crypto.subtle.encrypt(params, groupKey, input as BufferSource)
  return { ciphertext, nonce: b64(nonce) }
}

export async function decryptGroupBytes(groupKey: CryptoKey, ciphertext: ArrayBuffer | Uint8Array, nonce: string, conversationId?: number, keyEpoch?: number) {
  const iv = unb64(nonce)
  if (iv.length !== GCM_IV_BYTES) throw new Error('Invalid attachment nonce.')
  const params: AesGcmParams = { name: 'AES-GCM', iv: iv as BufferSource }
  if (conversationId !== undefined || keyEpoch !== undefined) {
    if (conversationId === undefined || keyEpoch === undefined) throw new Error('Conversation and epoch are required together.')
    params.additionalData = messageAad(conversationId, keyEpoch, 'attachment') as BufferSource
  }
  const input = ciphertext instanceof Uint8Array ? ciphertext : new Uint8Array(ciphertext)
  return window.crypto.subtle.decrypt(params, groupKey, input as BufferSource)
}
