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
const SCREEN_API_CACHE_TTL_MS = 2 * 60 * 1000
const screenApiCache = new Map<string, { value: any; fetchedAt: number }>()
const screenApiRefreshes = new Map<string, Promise<void>>()

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
    } catch { resolve(null) }
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
        if (!record || Date.now() - record.savedAt > PREPZA_OFFLINE_TTL_MS) { resolve(null); return }
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
    if (bytes > PREPZA_OFFLINE_MAX_BYTES) { db.close(); return }
    await new Promise<void>((resolve) => {
      const tx = db.transaction(PREPZA_OFFLINE_STORE, 'readwrite')
      tx.objectStore(PREPZA_OFFLINE_STORE).put({ key, savedAt: Date.now(), body })
      tx.oncomplete = () => resolve()
      tx.onerror = () => resolve()
      tx.onabort = () => resolve()
    })
  } catch {
    // Storage failure must never break the online request path.
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
    // Logout must not be blocked by local storage cleanup.
  } finally {
    try { db.close() } catch {}
  }
}

function isScreenCacheableApiRequest(path: string, method: string): boolean {
  if (method !== 'GET') return false
  if (path.startsWith('/documents/') || path.includes('/reading/')) return false
  return path.startsWith('/') && !path.startsWith('/socket.io/')
}

async function requestApiJson<T>(path: string, options: RequestInit): Promise<T> {
  const { headers: extraHeaders, ...restOptions } = options
  const res = await fetch(path, {
    credentials: 'include',
    ...restOptions,
    headers: { 'Content-Type': 'application/json', ...(extraHeaders || {}) },
  })
  let body: any = null
  try { body = await res.json() } catch { /* no JSON body */ }
  if (!res.ok) throw new ApiError((body && body.error) || `Request failed (${res.status})`, res.status)
  return body as T
}

function refreshScreenApiCache<T>(path: string, options: RequestInit): void {
  if (screenApiRefreshes.has(path)) return
  const refresh = requestApiJson<T>(path, options).then(fresh => {
    screenApiCache.set(path, { value: fresh, fetchedAt: Date.now() })
    void writePrepzaOffline(path, fresh)
  }).catch(() => {
    // Keep stale data usable when background refresh fails.
  }).finally(() => screenApiRefreshes.delete(path))
  screenApiRefreshes.set(path, refresh)
}

async function api<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const method = String(options.method || 'GET').toUpperCase()
  const cacheable = isScreenCacheableApiRequest(path, method)

  if (cacheable) {
    const cached = screenApiCache.get(path)
    if (cached) {
      if (Date.now() - cached.fetchedAt >= SCREEN_API_CACHE_TTL_MS) refreshScreenApiCache<T>(path, options)
      return cached.value as T
    }
  }

  try {
    const value = await requestApiJson<T>(path, options)
    if (cacheable) {
      screenApiCache.set(path, { value, fetchedAt: Date.now() })
      void writePrepzaOffline(path, value)
    }
    return value
  } catch (error) {
    if (cacheable) {
      const cached = await readPrepzaOffline<T>(path)
      if (cached !== null) {
        screenApiCache.set(path, { value: cached, fetchedAt: Date.now() })
        return cached
      }
    }
    throw error
  } finally {
    if (!cacheable && method !== 'GET') screenApiCache.clear()
  }
}'''

if OLD not in text:
    raise SystemExit('Offline data foundation failed: expected api helper was not found.')

text = text.replace(OLD, NEW, 1)
APP.write_text(text, encoding='utf-8')
print('Offline data foundation + cached-first loading policy applied and verified.')