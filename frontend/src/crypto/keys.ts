// frontend/src/crypto/keys.ts
//
// Chunk 1 (E2EE Foundation) - Chats identity keypair generation and local
// storage only. Deliberately does NOT call POST /keys/register or touch
// App.tsx - wiring this into login/signup happens in a later chunk, per
// the "foundation only, no chat behavior changes yet" scope for Chunk 1.
//
// Scope reminder: this covers Chats (Conversation/Message) only. Study
// Groups and Forum (@Ada) are unaffected and never touch this module.
//
// Algorithm: ECDH P-256, chosen because it's natively supported by
// WebCrypto's SubtleCrypto (no X25519 polyfill/library needed). The
// private key is generated as `extractable: true` so it can later be
// exported for the passphrase-wrapped backup blob (Chunk 2) - it is
// never sent anywhere in this chunk.

const DB_NAME = 'prepza-e2ee'
const DB_VERSION = 1
const STORE_NAME = 'identity-keys'
const RECORD_KEY_PREFIX = 'account:' // one identity keypair per Prepza account on this browser

export interface IdentityKeyRecord {
  publicKey: CryptoKey
  privateKey: CryptoKey
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION)
    req.onupgradeneeded = () => {
      const db = req.result
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME)
      }
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

async function idbGet<T>(storeName: string, key: string): Promise<T | undefined> {
  const db = await openDb()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, 'readonly')
    const req = tx.objectStore(storeName).get(key)
    req.onsuccess = () => resolve(req.result as T | undefined)
    req.onerror = () => reject(req.error)
  })
}

async function idbSet(storeName: string, key: string, value: unknown): Promise<void> {
  const db = await openDb()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, 'readwrite')
    tx.objectStore(storeName).put(value, key)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}

/**
 * Generates a fresh ECDH P-256 identity keypair. Both keys are
 * extractable - the public key needs to be exported to send to the
 * server, and the private key needs to be exportable for the future
 * passphrase-wrapped backup (Chunk 2). Extractable does NOT mean the
 * private key leaves the device in this chunk - nothing here uploads it.
 */
export async function generateIdentityKeyPair(): Promise<CryptoKeyPair> {
  return window.crypto.subtle.generateKey(
    { name: 'ECDH', namedCurve: 'P-256' },
    true,
    ['deriveKey', 'deriveBits'],
  )
}

/**
 * Exports a public key as raw bytes, base64url-encoded - a compact,
 * URL-safe string suitable for the public_key field POST /keys/register
 * expects (added by Chunk 1's backend patch).
 */
export async function exportPublicKeyBase64Url(publicKey: CryptoKey): Promise<string> {
  const raw = await window.crypto.subtle.exportKey('raw', publicKey)
  const bytes = new Uint8Array(raw)
  let binary = ''
  for (const b of bytes) binary += String.fromCharCode(b)
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

/** Imports a base64url-encoded raw P-256 public key published by another device. */
export async function importPeerPublicKey(value: string): Promise<CryptoKey> {
  if (typeof value !== 'string' || !value.trim()) throw new Error('Peer public key is missing.')
  const normalized = value.replace(/-/g, '+').replace(/_/g, '/')
  const padded = normalized + '='.repeat((4 - (normalized.length % 4)) % 4)
  let binary: string
  try {
    binary = atob(padded)
  } catch {
    throw new Error('Peer public key is not valid base64url.')
  }
  const bytes = Uint8Array.from(binary, char => char.charCodeAt(0))
  if (bytes.length !== 65 || bytes[0] !== 0x04) throw new Error('Peer public key is not a P-256 uncompressed key.')
  return window.crypto.subtle.importKey(
    'raw',
    bytes,
    { name: 'ECDH', namedCurve: 'P-256' },
    false,
    [],
  )
}

/** Persists the current device's identity keypair to IndexedDB. */
export async function storeIdentityKeyPair(keyPair: CryptoKeyPair): Promise<void> {
  await idbSet(STORE_NAME, RECORD_KEY, keyPair)
}

/**
 * Loads this device's identity keypair from IndexedDB, or null if none
 * has been generated yet on this device/browser.
 */
export async function loadIdentityKeyPair(): Promise<CryptoKeyPair | null> {
  const record = await idbGet<CryptoKeyPair>(STORE_NAME, RECORD_KEY)
  return record ?? null
}

/**
 * Returns this device's identity keypair, generating and persisting a
 * new one on first call if none exists yet on this device/browser. `isNew`
 * tells the caller (a later chunk) whether it needs to call
 * POST /keys/register - this function deliberately does not make that call
 * itself, keeping this module network-free per Chunk 1's scope.
 */
export async function getOrCreateIdentityKeyPair(): Promise<{
  keyPair: CryptoKeyPair
  isNew: boolean
}> {
  const existing = await loadIdentityKeyPair()
  if (existing) {
    return { keyPair: existing, isNew: false }
  }
  const keyPair = await generateIdentityKeyPair()
  await storeIdentityKeyPair(keyPair, userId)
  return { keyPair, isNew: true }
}
