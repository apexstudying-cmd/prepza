const DB_NAME = 'prepza-offline-v2'
const STORE = 'generatedMaterials'
const AUDIO_STORE = 'generatedAudio'
const USER_KEY = 'prepza-offline-user-id'
const MAX_GENERATED_ROWS = 80
const MAX_GENERATED_PAYLOAD_BYTES = 512 * 1024
const MAX_AUDIO_CACHE_BYTES = 80 * 1024 * 1024
const MAX_SINGLE_AUDIO_BYTES = 25 * 1024 * 1024

type StoredMaterial = { key: string; path: string; requestBody: unknown; payload: unknown; savedAt: number }
type StoredAudio = { key: string; userId: string; sourceUrl: string; blob: Blob; savedAt: number }

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 3)
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE, { keyPath: 'key' })
      if (!db.objectStoreNames.contains(AUDIO_STORE)) db.createObjectStore(AUDIO_STORE, { keyPath: 'key' })
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

/** Remove the remembered offline account after the server confirms that the session is no longer authenticated. */
export function clearOfflineUserId(): void {
  try { localStorage.removeItem(USER_KEY) } catch {}
}

function supported(path: string) {
  return path.includes('/documents/') && /(summarize|quiz|flashcards|podcast-script|podcast-audio|mind-map|mindmap)/.test(path)
}

export async function saveGeneratedMaterialOffline(path: string, requestBody: unknown, payload: unknown) {
  if (!supported(path)) return
  try { if (new Blob([JSON.stringify(payload ?? null)]).size > MAX_GENERATED_PAYLOAD_BYTES) return } catch { return }
  try {
    const db = await openDb()
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite')
      tx.objectStore(STORE).put({ key: keyFor(path, requestBody), path, requestBody, payload, savedAt: Date.now() } satisfies StoredMaterial)
      tx.oncomplete = () => resolve(); tx.onerror = () => reject(tx.error)
    })
    const rows = await readAll()
    const userId = localStorage.getItem(USER_KEY) || 'unknown'
    const userRows = rows.filter(row => row.key.startsWith(`${userId}:`)).sort((a,b) => a.savedAt-b.savedAt)
    if (userRows.length > MAX_GENERATED_ROWS) {
      const excess = userRows.slice(0, userRows.length - MAX_GENERATED_ROWS)
      const cleanupDb = await openDb()
      const tx = cleanupDb.transaction(STORE, 'readwrite'); for (const row of excess) tx.objectStore(STORE).delete(row.key)
      await new Promise<void>((resolve, reject) => { tx.oncomplete=()=>resolve(); tx.onerror=()=>reject(tx.error) })
      cleanupDb.close()
    }
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

export async function getLatestGeneratedMaterialForPath(path: string): Promise<any | null> {
  if (!supported(path)) return null
  try {
    const userId = localStorage.getItem(USER_KEY) || 'unknown'
    const rows = (await readAll()).filter(row => row.path === path && row.key.startsWith(`${userId}:`))
    rows.sort((a, b) => b.savedAt - a.savedAt)
    return rows[0]?.payload ?? null
  } catch (_) { return null }
}

export async function getGeneratedMaterialOffline(path: string, requestBody: unknown): Promise<any | null> {
  try { return (await readMatching(path, requestBody))[0]?.payload ?? null } catch (_) { return null }
}

export async function listGeneratedMaterialsOffline(path: string, requestBody: unknown): Promise<Array<{ payload: unknown; savedAt: number }>> {
  try { return (await readMatching(path, requestBody)).map(row => ({ payload: row.payload, savedAt: row.savedAt })) } catch (_) { return [] }
}

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

function audioKey(url: string) {
  return `${localStorage.getItem(USER_KEY) || 'unknown'}:${url}`
}

export async function cacheGeneratedAudioOffline(url: string): Promise<void> {
  if (!url) return
  try {
    const db = await openDb()
    const existing = await new Promise<StoredAudio | undefined>((resolve, reject) => {
      const tx = db.transaction(AUDIO_STORE, 'readonly')
      const request = tx.objectStore(AUDIO_STORE).get(audioKey(url))
      request.onsuccess = () => resolve(request.result as StoredAudio | undefined)
      request.onerror = () => reject(request.error)
    })
    if (existing?.blob instanceof Blob && existing.blob.size > 0) { db.close(); return }
    const response = await fetch(url, { credentials: 'include', cache: 'no-store' })
    if (!response.ok || response.type === 'opaque') { db.close(); return }
    const blob = await response.blob()
    if (!blob.size || blob.size > MAX_SINGLE_AUDIO_BYTES) { db.close(); return }
    const existingRows = await new Promise<StoredAudio[]>((resolve, reject) => { const tx = db.transaction(AUDIO_STORE, 'readonly'); const req = tx.objectStore(AUDIO_STORE).getAll(); req.onsuccess=()=>resolve((req.result as StoredAudio[])||[]); req.onerror=()=>reject(req.error) })
    const userId = localStorage.getItem(USER_KEY) || 'unknown'
    const used = existingRows.filter(x => x.userId === userId && x.key !== audioKey(url)).reduce((sum,x)=>sum+(x.blob?.size||0),0)
    if (used + blob.size > MAX_AUDIO_CACHE_BYTES) { db.close(); return }
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(AUDIO_STORE, 'readwrite')
      tx.objectStore(AUDIO_STORE).put({ key: audioKey(url), userId, sourceUrl: url, blob, savedAt: Date.now() } satisfies StoredAudio)
      tx.oncomplete = () => resolve(); tx.onerror = () => reject(tx.error)
    })
    db.close()
  } catch (_) {}
}

export async function getCachedGeneratedAudioUrl(url: string): Promise<string | null> {
  if (!url) return null
  try {
    const db = await openDb()
    const audio = await new Promise<StoredAudio | undefined>((resolve, reject) => {
      const tx = db.transaction(AUDIO_STORE, 'readonly')
      const request = tx.objectStore(AUDIO_STORE).get(audioKey(url))
      request.onsuccess = () => resolve(request.result as StoredAudio | undefined)
      request.onerror = () => reject(request.error)
    })
    db.close()
    if (!audio?.blob || audio.userId !== (localStorage.getItem(USER_KEY) || 'unknown')) return null
    return URL.createObjectURL(audio.blob)
  } catch (_) { return null }
}

export async function clearGeneratedAudioCache(): Promise<void> {
  try {
    const db = await openDb()
    const userId = localStorage.getItem(USER_KEY) || 'unknown'
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(AUDIO_STORE, 'readwrite')
      const store = tx.objectStore(AUDIO_STORE)
      const request = store.openCursor()
      request.onsuccess = () => {
        const cursor = request.result
        if (!cursor) { resolve(); return }
        const row = cursor.value as StoredAudio
        if (row.userId === userId) cursor.delete()
        cursor.continue()
      }
      request.onerror = () => reject(request.error)
    })
    db.close()
  } catch (_) {}
}
