// Local-only storage for decrypted group conversation keys.
// The server never receives these CryptoKey objects.
// Keys are retained by conversation + epoch so a membership rotation can
// protect future messages without destroying access to historical messages.

const DB_NAME = 'prepza-e2ee-groups'
const DB_VERSION = 2
const STORE_NAME = 'group-keys'

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION)
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME)
      }
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

function recordKey(conversationId: number, keyEpoch: number): string {
  return `${conversationId}:${keyEpoch}`
}

export async function storeGroupConversationKey(
  conversationId: number,
  keyEpoch: number,
  key: CryptoKey,
): Promise<void> {
  const db = await openDb()
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite')
    tx.objectStore(STORE_NAME).put({ key, keyEpoch }, recordKey(conversationId, keyEpoch))
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}

export async function loadGroupConversationKey(
  conversationId: number,
  keyEpoch: number,
): Promise<CryptoKey | null> {
  const db = await openDb()
  const store = db.transaction(STORE_NAME, 'readonly').objectStore(STORE_NAME)

  const exact = await new Promise<{ key: CryptoKey; keyEpoch: number } | undefined>((resolve, reject) => {
    const request = store.get(recordKey(conversationId, keyEpoch))
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
  if (exact?.key && exact.keyEpoch === keyEpoch) return exact.key

  // One-time compatibility path for keys created by the v1 store, which
  // used the bare conversation id as its IndexedDB key.
  const legacy = await new Promise<{ key: CryptoKey; keyEpoch: number } | undefined>((resolve, reject) => {
    const request = store.get(String(conversationId))
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
  if (!legacy || legacy.keyEpoch !== keyEpoch) return null

  await storeGroupConversationKey(conversationId, keyEpoch, legacy.key)
  return legacy.key
}

export async function deleteGroupConversationKey(conversationId: number): Promise<void> {
  const db = await openDb()
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite')
    const store = tx.objectStore(STORE_NAME)
    const request = store.openCursor()
    request.onsuccess = () => {
      const cursor = request.result
      if (!cursor) return
      if (String(cursor.key).startsWith(`${conversationId}:`) || String(cursor.key) === String(conversationId)) {
        cursor.delete()
      }
      cursor.continue()
    }
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}
