const DB_NAME = 'prepza-offline-v2'
const STORE = 'generatedMaterials'
const USER_KEY = 'prepza-offline-user-id'

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 2)
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE, { keyPath: 'key' })
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

function serializedBody(body: unknown) {
  try { return JSON.stringify(body ?? null) } catch { return '' }
}

function keyPrefix(path: string, body: unknown) {
  return `${localStorage.getItem(USER_KEY) || 'unknown'}:${path}:${serializedBody(body)}:`
}

function keyFor(path: string, body: unknown) {
  return `${keyPrefix(path, body)}${Date.now()}:${Math.random().toString(36).slice(2)}`
}

export function setOfflineUserId(userId: number) {
  try { localStorage.setItem(USER_KEY, String(userId)) } catch {}
}

export async function saveGeneratedMaterialOffline(path: string, requestBody: unknown, payload: unknown) {
  if (!path.includes('/documents/') || !/(summarize|quiz|flashcards|podcast-script|mind-map)/.test(path)) return
  try {
    const db = await openDb()
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite')
      tx.objectStore(STORE).put({ key: keyFor(path, requestBody), path, requestBody, payload, savedAt: Date.now() })
      tx.oncomplete = () => resolve(); tx.onerror = () => reject(tx.error)
    })
    db.close()
  } catch (_) {}
}

export async function getGeneratedMaterialOffline(path: string, requestBody: unknown): Promise<any | null> {
  if (!path.includes('/documents/') || !/(summarize|quiz|flashcards|podcast-script|mind-map)/.test(path)) return null
  try {
    const db = await openDb()
    const prefix = keyPrefix(path, requestBody)
    const value = await new Promise<any | null>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readonly')
      const request = tx.objectStore(STORE).openCursor()
      let latest: any = null
      request.onsuccess = () => {
        const cursor = request.result
        if (!cursor) { resolve(latest?.payload ?? null); return }
        const row = cursor.value
        if (typeof row?.key === 'string' && row.key.startsWith(prefix) && (!latest || Number(row.savedAt) > Number(latest.savedAt))) latest = row
        cursor.continue()
      }
      request.onerror = () => reject(request.error)
    })
    db.close(); return value
  } catch (_) { return null }
}
