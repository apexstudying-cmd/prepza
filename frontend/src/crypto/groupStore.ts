// Local-only storage for decrypted group conversation keys.
// The server never receives these CryptoKey objects.

const DB_NAME = 'prepza-e2ee'
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

export async function storeGroupConversationKey(
  conversationId: number,
  keyEpoch: number,
  key: CryptoKey,
): Promise<void> {
  const db = await openDb()
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite')
    tx.objectStore(STORE_NAME).put({ key, keyEpoch }, String(conversationId))
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}

export async function loadGroupConversationKey(
  conversationId: number,
  keyEpoch: number,
): Promise<CryptoKey | null> {
  const db = await openDb()
  const record = await new Promise<{ key: CryptoKey; keyEpoch: number } | undefined>((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readonly')
    const request = tx.objectStore(STORE_NAME).get(String(conversationId))
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
  if (!record || record.keyEpoch !== keyEpoch) return null
  return record.key
}

export async function deleteGroupConversationKey(conversationId: number): Promise<void> {
  const db = await openDb()
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite')
    tx.objectStore(STORE_NAME).delete(String(conversationId))
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}
