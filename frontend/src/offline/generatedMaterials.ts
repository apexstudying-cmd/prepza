const DB_NAME = 'prepza-offline-v2'
const STORE = 'generatedMaterials'
const USER_KEY = 'prepza-offline-user-id'
const AUDIO_CACHE = 'prepza-generated-audio-v1'

type StoredMaterial = { key: string; path: string; requestBody: unknown; payload: unknown; savedAt: number }

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

export function getOfflineUserId(): string | null {
  try { return localStorage.getItem(USER_KEY) } catch { return null }
}

function supported(path: string) {
  return path.includes('/documents/') && /(summarize|quiz|flashcards|podcast-script|podcast-audio|mind-map)/.test(path)
}

export async function saveGeneratedMaterialOffline(path: string, requestBody: unknown, payload: unknown) {
  if (!supported(path)) return
  try {
    const db = await openDb()
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite')
      tx.objectStore(STORE).put({ key: keyFor(path, requestBody), path, requestBody, payload, savedAt: Date.now() } satisfies StoredMaterial)
      tx.oncomplete = () => resolve(); tx.onerror = () => reject(tx.error)
    })
    db.close()
  } catch (_) {}
}

async function readAll(): Promise<StoredMaterial[]> {
  const db = await openDb()
  try {
    return await new Promise<StoredMaterial[]>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readonly')
      const request = tx.objectStore(STORE).getAll()
      request.onsuccess = () => resolve((request.result as StoredMaterial[]) || [])
      request.onerror = () => reject(request.error)
    })
  } finally { db.close() }
}

async function readMatching(path: string, requestBody: unknown): Promise<StoredMaterial[]> {
  if (!supported(path)) return []
  const db = await openDb()
  try {
    return await new Promise<StoredMaterial[]>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readonly')
      const request = tx.objectStore(STORE).openCursor()
      const prefix = keyPrefix(path, requestBody)
      const rows: StoredMaterial[] = []
      request.onsuccess = () => {
        const cursor = request.result
        if (!cursor) { rows.sort((a, b) => b.savedAt - a.savedAt); resolve(rows); return }
        const row = cursor.value as StoredMaterial
        if (typeof row?.key === 'string' && row.key.startsWith(prefix)) rows.push(row)
        cursor.continue()
      }
      request.onerror = () => reject(request.error)
    })
  } finally { db.close() }
}

/** Latest saved generation for an endpoint, regardless of its original request body. */
export async function getLatestGeneratedMaterialForPath(path: string): Promise<any | null> {
  if (!supported(path)) return null
  try {
    const userId = localStorage.getItem(USER_KEY) || 'unknown'
    const rows = (await readAll()).filter(row => row.path === path && row.key.startsWith(`${userId}:`))
    rows.sort((a, b) => b.savedAt - a.savedAt)
    return rows[0]?.payload ?? null
  } catch (_) { return null }
}

/** Latest saved generation, preserving older generations in IndexedDB. */
export async function getGeneratedMaterialOffline(path: string, requestBody: unknown): Promise<any | null> {
  try { return (await readMatching(path, requestBody))[0]?.payload ?? null } catch (_) { return null }
}

/** Full saved generation history, newest first. */
export async function listGeneratedMaterialsOffline(path: string, requestBody: unknown): Promise<Array<{ payload: unknown; savedAt: number }>> {
  try { return (await readMatching(path, requestBody)).map(row => ({ payload: row.payload, savedAt: row.savedAt })) } catch (_) { return [] }
}

/** Removes one exact saved generation without affecting newer/older copies. */
export async function deleteGeneratedMaterialOffline(path: string, requestBody: unknown, savedAt: number): Promise<void> {
  try {
    const rows = await readMatching(path, requestBody)
    const target = rows.find(row => row.savedAt === savedAt)
    if (!target) return
    const db = await openDb()
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite')
      tx.objectStore(STORE).delete(target.key)
      tx.oncomplete = () => resolve(); tx.onerror = () => reject(tx.error)
    })
    db.close()
  } catch (_) {}
}

/** Cache generated podcast audio bytes so playback remains possible after a signed URL expires or while offline. */
export async function cacheGeneratedAudioOffline(url: string): Promise<void> {
  if (!url || typeof caches === 'undefined') return
  try {
    const cache = await caches.open(AUDIO_CACHE)
    const existing = await cache.match(url)
    if (existing) return
    const response = await fetch(url, { credentials: 'include' })
    if (response.ok || response.type === 'opaque') await cache.put(url, response.clone())
  } catch (_) {}
}

/** Return a local object URL for previously cached podcast audio. Caller owns the URL and should revoke it when no longer needed. */
export async function getCachedGeneratedAudioUrl(url: string): Promise<string | null> {
  if (!url || typeof caches === 'undefined') return null
  try {
    const cache = await caches.open(AUDIO_CACHE)
    const response = await cache.match(url)
    if (!response) return null
    const blob = await response.blob()
    return URL.createObjectURL(blob)
  } catch (_) { return null }
}

export async function clearGeneratedAudioCache(): Promise<void> {
  if (typeof caches === 'undefined') return
  try { await caches.delete(AUDIO_CACHE) } catch (_) {}
}
