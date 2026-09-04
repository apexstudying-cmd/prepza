// frontend/src/crypto/conversation.ts
//
// Chunk 3 (1:1 Chat Encryption) - derives a per-conversation AES key
// directly from static ECDH between two participants' identity keys
// (see keys.ts), with no key storage, wrapping, or server round-trip.
//
// Why this works: ECDH(myPrivateKey, peerPublicKey) produces the exact
// same shared secret as ECDH(peerPrivateKey, myPublicKey) - it's
// symmetric regardless of who computes it. Both participants derive the
// identical conversation key independently. HKDF with the conversation
// id as salt keeps each conversation's key distinct even between the
// same two people (relevant once/if a pair can have more than one
// conversation).
//
// Deliberately 1:1 only. Group chats need a genuinely different
// mechanism (no single shared secret across 3+ people) - that's the
// wrap-and-store ConversationKey approach, reserved for the group chat
// key distribution chunk.
//
// This module is pure crypto - no network calls, no App.tsx wiring.
// Callers (a later step) are responsible for fetching the peer's public
// key via GET /keys/<user_id> and passing it in here.

const HKDF_INFO = 'prepza-chat-v1'
const GCM_IV_BYTES = 12 // 96-bit IV, standard for AES-GCM

function base64UrlToUint8Array(b64url: string): Uint8Array {
  const b64 = b64url.replace(/-/g, '+').replace(/_/g, '/')
  const padded = b64 + '='.repeat((4 - (b64.length % 4)) % 4)
  const binary = atob(padded)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
  return bytes
}

function base64ToUint8Array(b64: string): Uint8Array {
  const binary = atob(b64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
  return bytes
}

function arrayBufferToBase64(buf: ArrayBuffer | Uint8Array): string {
  const bytes = buf instanceof Uint8Array ? buf : new Uint8Array(buf)
  let binary = ''
  for (const b of bytes) binary += String.fromCharCode(b)
  return btoa(binary)
}

/**
 * Imports a peer's public key from the base64url string returned by
 * GET /keys/<user_id> (produced by keys.ts's exportPublicKeyBase64Url
 * on their device) back into a usable CryptoKey.
 */
export async function importPeerPublicKey(publicKeyBase64Url: string): Promise<CryptoKey> {
  const raw = base64UrlToUint8Array(publicKeyBase64Url)
  return window.crypto.subtle.importKey(
    'raw',
    raw as BufferSource,
    { name: 'ECDH', namedCurve: 'P-256' },
    true,
    [],
  )
}

/**
 * Derives the shared 1:1 conversation encryption key from my private
 * key and the peer's public key, salted with the conversation id so
 * the same pair of people get a distinct key per conversation.
 *
 * Both participants call this with their OWN private key and the
 * OTHER person's public key, and arrive at the identical AES-GCM key -
 * that's the whole point of static-static ECDH.
 */
export async function deriveConversationKey(
  myPrivateKey: CryptoKey,
  peerPublicKey: CryptoKey,
  conversationId: number,
): Promise<CryptoKey> {
  const sharedBits = await window.crypto.subtle.deriveBits(
    { name: 'ECDH', public: peerPublicKey } as EcdhKeyDeriveParams,
    myPrivateKey,
    256,
  )
  const hkdfBaseKey = await window.crypto.subtle.importKey('raw', sharedBits, 'HKDF', false, ['deriveKey'])

  const encoder = new TextEncoder()
  const salt = encoder.encode(String(conversationId))
  const info = encoder.encode(HKDF_INFO)

  return window.crypto.subtle.deriveKey(
    { name: 'HKDF', hash: 'SHA-256', salt: salt as BufferSource, info: info as BufferSource },
    hkdfBaseKey,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt', 'decrypt'],
  )
}

export interface EncryptedMessageBody {
  body: string // base64 ciphertext - goes in the "body" field of POST /chats/:id/messages
  nonce: string // base64 IV - goes in the "nonce" field, required alongside body
}

/** Encrypts a plaintext message body for sending. */
export async function encryptMessageBody(
  conversationKey: CryptoKey,
  plaintext: string,
): Promise<EncryptedMessageBody> {
  const iv = window.crypto.getRandomValues(new Uint8Array(GCM_IV_BYTES))
  const encoder = new TextEncoder()
  const ciphertext = await window.crypto.subtle.encrypt(
    { name: 'AES-GCM', iv: iv as BufferSource },
    conversationKey,
    encoder.encode(plaintext),
  )
  return {
    body: arrayBufferToBase64(ciphertext),
    nonce: arrayBufferToBase64(iv),
  }
}

/**
 * Decrypts a message body fetched from GET /chats/:id/messages. Throws
 * on the wrong key or a corrupted/tampered blob (AES-GCM authentication
 * failure) - callers should catch this and show a "couldn't decrypt
 * this message" placeholder rather than crash the whole thread render.
 */
export async function decryptMessageBody(
  conversationKey: CryptoKey,
  encryptedBody: string,
  nonce: string,
): Promise<string> {
  const iv = base64ToUint8Array(nonce)
  const ciphertext = base64ToUint8Array(encryptedBody)
  const plaintextBuf = await window.crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: iv as BufferSource },
    conversationKey,
    ciphertext as BufferSource,
  )
  return new TextDecoder().decode(plaintextBuf)
}
