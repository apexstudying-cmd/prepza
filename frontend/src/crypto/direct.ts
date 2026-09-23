// Direct-chat E2EE primitives for Prepza.
// P-256 ECDH derives a stable per-conversation AES-256-GCM key.
// The server receives only ciphertext + nonce; it never receives this key.

const GCM_IV_BYTES = 12
const HKDF_INFO = 'prepza-direct-chat-v1'

function b64(buf: ArrayBuffer | Uint8Array): string {
  const bytes = buf instanceof Uint8Array ? buf : new Uint8Array(buf)
  let out = ''
  for (const byte of bytes) out += String.fromCharCode(byte)
  return btoa(out)
}

function unb64(value: string): Uint8Array {
  if (typeof value !== 'string' || !value || !/^[A-Za-z0-9+/]*={0,2}$/.test(value) || value.length % 4 === 1) {
    throw new Error('Invalid ciphertext encoding.')
  }
  const binary = atob(value)
  return Uint8Array.from(binary, char => char.charCodeAt(0))
}

function assertId(value: number, label: string) {
  if (!Number.isInteger(value) || value <= 0) throw new Error(`Invalid ${label}.`)
}

function aad(conversationId: number, purpose: string): Uint8Array {
  assertId(conversationId, 'conversation id')
  if (!purpose || purpose.length > 64) throw new Error('Invalid crypto purpose.')
  return new TextEncoder().encode(`prepza:direct:${purpose}:v1:${conversationId}`)
}

export async function deriveDirectChatKey(
  myPrivateKey: CryptoKey,
  peerPublicKey: CryptoKey,
  conversationId: number,
  myUserId: number,
  peerUserId: number,
): Promise<CryptoKey> {
  assertId(conversationId, 'conversation id')
  assertId(myUserId, 'user id')
  assertId(peerUserId, 'peer user id')
  if (myUserId === peerUserId) throw new Error('A direct chat needs two different users.')

  const sharedBits = await window.crypto.subtle.deriveBits(
    { name: 'ECDH', public: peerPublicKey } as EcdhKeyDeriveParams,
    myPrivateKey,
    256,
  )
  const base = await window.crypto.subtle.importKey('raw', sharedBits, 'HKDF', false, ['deriveKey'])
  const ids = [myUserId, peerUserId].sort((a, b) => a - b).join(':')
  return window.crypto.subtle.deriveKey(
    {
      name: 'HKDF',
      hash: 'SHA-256',
      salt: new TextEncoder().encode(`${conversationId}:${ids}`) as BufferSource,
      info: new TextEncoder().encode(HKDF_INFO) as BufferSource,
    },
    base,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt', 'decrypt'],
  )
}

export async function encryptDirectMessage(key: CryptoKey, plaintext: string, conversationId: number) {
  const nonce = window.crypto.getRandomValues(new Uint8Array(GCM_IV_BYTES))
  const ciphertext = await window.crypto.subtle.encrypt(
    { name: 'AES-GCM', iv: nonce as BufferSource, additionalData: aad(conversationId, 'message') as BufferSource },
    key,
    new TextEncoder().encode(plaintext),
  )
  return { body: b64(ciphertext), nonce: b64(nonce) }
}

export async function decryptDirectMessage(key: CryptoKey, body: string, nonce: string, conversationId: number) {
  const iv = unb64(nonce)
  if (iv.length !== GCM_IV_BYTES) throw new Error('Invalid message nonce.')
  const plaintext = await window.crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: iv as BufferSource, additionalData: aad(conversationId, 'message') as BufferSource },
    key,
    unb64(body) as BufferSource,
  )
  return new TextDecoder().decode(plaintext)
}

export async function encryptDirectBytes(key: CryptoKey, bytes: ArrayBuffer | Uint8Array, conversationId: number) {
  const nonce = window.crypto.getRandomValues(new Uint8Array(GCM_IV_BYTES))
  const input = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes)
  const ciphertext = await window.crypto.subtle.encrypt(
    { name: 'AES-GCM', iv: nonce as BufferSource, additionalData: aad(conversationId, 'attachment') as BufferSource },
    key,
    input as BufferSource,
  )
  return { ciphertext, nonce: b64(nonce) }
}

export async function decryptDirectBytes(key: CryptoKey, bytes: ArrayBuffer | Uint8Array, nonce: string, conversationId: number) {
  const iv = unb64(nonce)
  if (iv.length !== GCM_IV_BYTES) throw new Error('Invalid attachment nonce.')
  const input = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes)
  return window.crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: iv as BufferSource, additionalData: aad(conversationId, 'attachment') as BufferSource },
    key,
    input as BufferSource,
  )
}
