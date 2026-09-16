from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'frontend' / 'src' / 'App.tsx'
text = APP.read_text(encoding='utf-8')

MARKER = "const PREPZA_OFFLINE_DB = 'prepza-offline-v1'"
if MARKER in text:
    print('Offline data foundation already applied.')
    raise SystemExit(0)

OLD = '''async function api<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const { headers: extraHeaders, ...restOptions } = options
  const res = await fetch(path, {
    credentials: 'include',
    ...restOptions,
    headers: { 'Content-Type': 'application/json', ...(extraHeaders || {}) },
  })
  let body: any = null
  try { body = await res.json() } catch { /* no JSON body */ }
  if (!res.ok) {
    throw new ApiError((body && body.error) || `Request failed (${res.status})`, res.status)
  }
  return body as T
}'''

NEW = '''const PREPZA_OFFLINE_DB = 'prepza-offline-v1'
const PREPZA_OFFLINE_STORE = 'responses'
const PREPZA_OFFLINE_TTL_MS = 7 * 24 * 60 * 60 * 1000
const PREPZA_OFFLINE_MAX_BYTES = 2 * 1024 * 1024

// O2: persistent, structured local data. The service worker owns the app
// shell; IndexedDB owns JSON data that belongs to the signed-in device.
// This layer is deliberately small and dependency-free so it works in the
// PWA on Android as well as ordinary browsers.
function openPrepzaOfflineDb(): Promise<IDBDatabase | null> {
  if (typeof indexedDB === 'undefined') return Promise.resolve(null)
  return new Promise((resolve) => {
    try {
      const request = indexedDB.open(PREPZA_OFFLINE_DB, 1)
      request.onupgradeneeded = () => {
        const db = request.result
        if (!db.objectStoreNames.contains(PREPZA_OFFLINE_STORE)) {
          db.createObjectStore(PREPZA_OFFLINE_STORE, { keyPath: 'key' })
        }
      }
      request.onsuccess = () => resolve(request.result)
      request.onerror = () => resolve(null)
      request.onblocked = () => resolve(null)
    } catch {
      resolve(null)
    }
  })
}

async function readPrepzaOffline<T>(key: string): Promise<T | null> {
  const db = await openPrepzaOfflineDb()
  if (!db) return null
  return new Promise((resolve) => {
    try {
      const tx = db.transaction(PREPZA_OFFLINE_STORE, 'readonly')
      const request = tx.objectStore(PREPZA_OFFLINE_STORE).get(key)
      request.onsuccess = () => {
        const record = request.result as { key: string; savedAt: number; body: T } | undefined
        if (!record || Date.now() - record.savedAt > PREPZA_OFFLINE_TTL_MS) {
          resolve(null)
          return
        }
        resolve(record.body)
      }
      request.onerror = () => resolve(null)
      tx.oncomplete = () => db.close()
      tx.onerror = () => { try { db.close() } catch {} }
    } catch {
      try { db.close() } catch {}
      resolve(null)
    }
  })
}

async function writePrepzaOffline<T>(key: string, body: T): Promise<void> {
  const db = await openPrepzaOfflineDb()
  if (!db) return
  try {
    const bytes = new Blob([JSON.stringify(body)]).size
    if (bytes > PREPZA_OFFLINE_MAX_BYTES) {
      db.close()
      return
    }
    await new Promise<void>((resolve) => {
      const tx = db.transaction(PREPZA_OFFLINE_STORE, 'readwrite')
      tx.objectStore(PREPZA_OFFLINE_STORE).put({ key, savedAt: Date.now(), body })
      tx.oncomplete = () => resolve()
      tx.onerror = () => resolve()
      tx.onabort = () => resolve()
    })
  } catch {
    // Offline storage is an enhancement; a quota/security failure must never
    // break the online request path.
  } finally {
    try { db.close() } catch {}
  }
}

async function clearPrepzaOfflineData(): Promise<void> {
  const db = await openPrepzaOfflineDb()
  if (!db) return
  try {
    await new Promise<void>((resolve) => {
      const tx = db.transaction(PREPZA_OFFLINE_STORE, 'readwrite')
      tx.objectStore(PREPZA_OFFLINE_STORE).clear()
      tx.oncomplete = () => resolve()
      tx.onerror = () => resolve()
      tx.onabort = () => resolve()
    })
  } catch {
    // Best-effort cleanup; logout itself must not be blocked by local storage.
  } finally {
    try { db.close() } catch {}
  }
}

async function api<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const { headers: extraHeaders, ...restOptions } = options
  const method = String(restOptions.method || 'GET').toUpperCase()
  const cacheKey = path
  const canUseOfflineData = method === 'GET' && path.startsWith('/') && !path.startsWith('/socket.io/')

  try {
    const res = await fetch(path, {
      credentials: 'include',
      ...restOptions,
      headers: { 'Content-Type': 'application/json', ...(extraHeaders || {}) },
    })
    let body: any = null
    try { body = await res.json() } catch { /* no JSON body */ }
    if (!res.ok) {
      throw new ApiError((body && body.error) || `Request failed (${res.status})`, res.status)
    }
    if (canUseOfflineData && body !== null) {
      void writePrepzaOffline(cacheKey, body)
    }
    return body as T
  } catch (error) {
    if (canUseOfflineData) {
      const cached = await readPrepzaOffline<T>(cacheKey)
      if (cached !== null) return cached
    }
    throw error
  }
}'''

if OLD not in text:
    raise SystemExit('Offline data foundation failed: expected api helper was not found.')

text = text.replace(OLD, NEW, 1)
APP.write_text(text, encoding='utf-8')
print('Offline data foundation applied and verified.')