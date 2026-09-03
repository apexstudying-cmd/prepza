// frontend/src/crypto/backup.ts
//
// Chunk 2 (E2EE Passphrase Backup) - wraps/unwraps a Chats identity
// private key (from keys.ts) with a user-chosen passphrase, so it can be
// backed up server-side as ciphertext and recovered on a new device.
// Deliberately does NOT call POST/GET /keys/backup itself - wiring this
// into an actual "set up secure chat backup" UI flow and the recovery
// flow on a new device happens in a later chunk. This module is pure
// crypto + encoding, no network calls, same isolation as keys.ts.
//
// Algorithm: PBKDF2-HMAC-SHA256 (native WebCrypto, no WASM dependency)
// deriving an AES-256-GCM key from the passphrase + a random salt.
// Iteration count follows OWASP's 2023 PBKDF2-SHA256 recommendation.
//
// If the passphrase is lost, the blob is permanently undecryptable -
// there is no server-side recovery path, by design (see the E2EE
// design doc, section 2.2). That tradeoff is a UI/copy concern for the
// onboarding chunk, not something this module can or should soften.

const PBKDF2_ITERATIONS = 310_000
const SALT_BYTES = 16
const AES_KEY_LENGTH = 256

export interface WrappedKeyBlob {
  encryptedPrivateKey: string // base64: iv + ciphertext, concatenated
  kdfSalt: string // base64
}

function arrayBufferToBase64(buf: ArrayBuffer | Uint8Array): string {
  const bytes = buf instanceof Uint8Array ? buf : new Uint8Array(buf)
  let binary = ''
  for (const b of bytes) binary += String.fromCharCode(b)
  return btoa(binary)
}

function base64ToUint8Array(b64: string): Uint8Array {
  const binary = atob(b64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
  return bytes
}

function generateSalt(): Uint8Array {
  return window.crypto.getRandomValues(new Uint8Array(SALT_BYTES))
}

async function deriveWrappingKey(passphrase: string, salt: Uint8Array): Promise<CryptoKey> {
  const encoder = new TextEncoder()
  const baseKey = await window.crypto.subtle.importKey(
    'raw',
    encoder.encode(passphrase),
    'PBKDF2',
    false,
    ['deriveKey'],
  )
  return window.crypto.subtle.deriveKey(
    { name: 'PBKDF2', salt: salt as BufferSource, iterations: PBKDF2_ITERATIONS, hash: 'SHA-256' },
    baseKey,
    { name: 'AES-GCM', length: AES_KEY_LENGTH },
    false,
    ['encrypt', 'decrypt'],
  )
}

/**
 * Wraps (encrypts) a Chats identity private key with a user-chosen
 * passphrase. Exports the private key as JWK, encrypts it with an
 * AES-GCM key derived from the passphrase via PBKDF2, and returns the
 * two base64 strings the backend's POST /keys/backup expects.
 *
 * A fresh random salt is generated on every call - re-wrapping (e.g.
 * after a passphrase change) should always call this again rather than
 * reusing a previously stored salt.
 */
export async function wrapPrivateKeyWithPassphrase(
  privateKey: CryptoKey,
  passphrase: string,
): Promise<WrappedKeyBlob> {
  const salt = generateSalt()
  const wrappingKey = await deriveWrappingKey(passphrase, salt)

  const jwk = await window.crypto.subtle.exportKey('jwk', privateKey)
  const plaintext = new TextEncoder().encode(JSON.stringify(jwk))

  const iv = window.crypto.getRandomValues(new Uint8Array(12)) // 96-bit IV, standard for AES-GCM
  const ciphertext = await window.crypto.subtle.encrypt({ name: 'AES-GCM', iv }, wrappingKey, plaintext)

  // Concatenate iv + ciphertext into one blob so the backend only needs
  // to store/return a single opaque string per field, matching the
  // encrypted_private_key column shape from Chunk 1.
  const combined = new Uint8Array(iv.length + ciphertext.byteLength)
  combined.set(iv, 0)
  combined.set(new Uint8Array(ciphertext), iv.length)

  return {
    encryptedPrivateKey: arrayBufferToBase64(combined),
    kdfSalt: arrayBufferToBase64(salt),
  }
}

/**
 * Unwraps (decrypts) a backup blob fetched from GET /keys/backup back
 * into a usable CryptoKey, given the same passphrase used to wrap it.
 * Throws if the passphrase is wrong (AES-GCM authentication failure) -
 * callers should catch this and show a "wrong passphrase" message
 * rather than a generic error, since that's the only realistic failure
 * mode here short of a corrupted blob.
 */
export async function unwrapPrivateKeyWithPassphrase(
  blob: WrappedKeyBlob,
  passphrase: string,
): Promise<CryptoKey> {
  const salt = base64ToUint8Array(blob.kdfSalt)
  const wrappingKey = await deriveWrappingKey(passphrase, salt)

  const combined = base64ToUint8Array(blob.encryptedPrivateKey)
  const iv = combined.slice(0, 12)
  const ciphertext = combined.slice(12)

  const plaintext = await window.crypto.subtle.decrypt({ name: 'AES-GCM', iv }, wrappingKey, ciphertext)
  const jwk = JSON.parse(new TextDecoder().decode(plaintext))

  return window.crypto.subtle.importKey(
    'jwk',
    jwk,
    { name: 'ECDH', namedCurve: 'P-256' },
    true,
    ['deriveKey', 'deriveBits'],
  )
}
