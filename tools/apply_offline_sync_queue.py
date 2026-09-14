from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'frontend' / 'src' / 'App.tsx'
text = APP.read_text(encoding='utf-8')

MARKER = "const PREPZA_OFFLINE_QUEUE_STORE = 'syncQueue'"
if MARKER in text:
    print('Offline sync queue foundation already applied.')
    raise SystemExit(0)

DB_MARKER = "const PREPZA_OFFLINE_DB = 'prepza-offline-v1'"
if DB_MARKER not in text:
    raise SystemExit('Offline sync queue failed: O2 IndexedDB foundation was not applied before O3.')

text = text.replace(
    "const PREPZA_OFFLINE_DB = 'prepza-offline-v1'",
    "const PREPZA_OFFLINE_DB = 'prepza-offline-v1'\nconst PREPZA_OFFLINE_QUEUE_STORE = 'syncQueue'\nconst PREPZA_OFFLINE_QUEUE_MAX_ATTEMPTS = 8\nconst PREPZA_OFFLINE_QUEUE_BASE_DELAY_MS = 2_000",
    1,
)

text = text.replace(
    "const request = indexedDB.open(PREPZA_OFFLINE_DB, 1)",
    "const request = indexedDB.open(PREPZA_OFFLINE_DB, 2)",
    1,
)

old_upgrade = """      request.onupgradeneeded = () => {
        const db = request.result
        if (!db.objectStoreNames.contains(PREPZA_OFFLINE_STORE)) {
          db.createObjectStore(PREPZA_OFFLINE_STORE, { keyPath: 'key' })
        }
      }"""
new_upgrade = """      request.onupgradeneeded = () => {
        const db = request.result
        if (!db.objectStoreNames.contains(PREPZA_OFFLINE_STORE)) {
          db.createObjectStore(PREPZA_OFFLINE_STORE, { keyPath: 'key' })
        }
        if (!db.objectStoreNames.contains(PREPZA_OFFLINE_QUEUE_STORE)) {
          const queue = db.createObjectStore(PREPZA_OFFLINE_QUEUE_STORE, { keyPath: 'id', autoIncrement: true })
          queue.createIndex('nextAttemptAt', 'nextAttemptAt', { unique: false })
        }
      }"""
if old_upgrade not in text:
    raise SystemExit('Offline sync queue failed: O2 IndexedDB upgrade block was not found.')
text = text.replace(old_upgrade, new_upgrade, 1)

anchor = "async function clearPrepzaOfflineData(): Promise<void> {"
idx = text.find(anchor)
if idx < 0:
    raise SystemExit('Offline sync queue failed: clearPrepzaOfflineData anchor was not found.')

queue_code = r'''type PrepzaOfflineQueueItem = {
  id?: number
  path: string
  method: string
  headers: Record<string, string>
  body: string | null
  createdAt: number
  attempts: number
  nextAttemptAt: number
  lastError: string | null
}

function prepzaOfflineQueueChanged(): void {
  try { window.dispatchEvent(new CustomEvent('prepza:offline-queue-changed')) } catch {}
}

async function enqueuePrepzaOfflineMutation(path: string, options: RequestInit = {}): Promise<number | null> {
  if (typeof indexedDB === 'undefined') return null
  const method = String(options.method || 'GET').toUpperCase()
  if (method === 'GET' || method === 'HEAD' || method === 'OPTIONS') return null
  const body = typeof options.body === 'string' ? options.body : options.body == null ? null : null
  if (options.body != null && body == null) return null

  const rawHeaders = options.headers as Record<string, string> | undefined
  const headers: Record<string, string> = {}
  Object.entries(rawHeaders || {}).forEach(([key, value]) => {
    const lower = key.toLowerCase()
    // Credentials and one-shot browser headers must never become durable queue data.
    if (lower !== 'authorization' && lower !== 'cookie' && lower !== 'x-prepza-offline-queue') {
      headers[key] = String(value)
    }
  })

  const db = await openPrepzaOfflineDb()
  if (!db) return null
  try {
    const id = await new Promise<number | null>((resolve) => {
      const tx = db.transaction(PREPZA_OFFLINE_QUEUE_STORE, 'readwrite')
      const request = tx.objectStore(PREPZA_OFFLINE_QUEUE_STORE).add({
        path,
        method,
        headers,
        body,
        createdAt: Date.now(),
        attempts: 0,
        nextAttemptAt: Date.now(),
        lastError: null,
      } satisfies PrepzaOfflineQueueItem)
      request.onsuccess = () => resolve(Number(request.result))
      request.onerror = () => resolve(null)
      tx.onerror = () => resolve(null)
      tx.onabort = () => resolve(null)
    })
    prepzaOfflineQueueChanged()
    return id
  } catch {
    return null
  } finally {
    try { db.close() } catch {}
  }
}

async function readPrepzaOfflineQueue(): Promise<PrepzaOfflineQueueItem[]> {
  const db = await openPrepzaOfflineDb()
  if (!db) return []
  return new Promise((resolve) => {
    try {
      const tx = db.transaction(PREPZA_OFFLINE_QUEUE_STORE, 'readonly')
      const request = tx.objectStore(PREPZA_OFFLINE_QUEUE_STORE).getAll()
      request.onsuccess = () => resolve((request.result || []) as PrepzaOfflineQueueItem[])
      request.onerror = () => resolve([])
      tx.oncomplete = () => db.close()
      tx.onerror = () => { try { db.close() } catch {} }
    } catch {
      try { db.close() } catch {}
      resolve([])
    }
  })
}

async function updatePrepzaOfflineQueueItem(item: PrepzaOfflineQueueItem): Promise<void> {
  if (item.id == null) return
  const db = await openPrepzaOfflineDb()
  if (!db) return
  try {
    await new Promise<void>((resolve) => {
      const tx = db.transaction(PREPZA_OFFLINE_QUEUE_STORE, 'readwrite')
      tx.objectStore(PREPZA_OFFLINE_QUEUE_STORE).put(item)
      tx.oncomplete = () => resolve()
      tx.onerror = () => resolve()
      tx.onabort = () => resolve()
    })
  } finally {
    try { db.close() } catch {}
  }
}

async function deletePrepzaOfflineQueueItem(id: number): Promise<void> {
  const db = await openPrepzaOfflineDb()
  if (!db) return
  try {
    await new Promise<void>((resolve) => {
      const tx = db.transaction(PREPZA_OFFLINE_QUEUE_STORE, 'readwrite')
      tx.objectStore(PREPZA_OFFLINE_QUEUE_STORE).delete(id)
      tx.oncomplete = () => resolve()
      tx.onerror = () => resolve()
      tx.onabort = () => resolve()
    })
  } finally {
    try { db.close() } catch {}
  }
}

let prepzaOfflineQueueFlushPromise: Promise<void> | null = null

async function flushPrepzaOfflineQueue(): Promise<void> {
  if (!navigator.onLine || prepzaOfflineQueueFlushPromise) return prepzaOfflineQueueFlushPromise || Promise.resolve()
  prepzaOfflineQueueFlushPromise = (async () => {
    try {
      const items = (await readPrepzaOfflineQueue())
        .filter(item => item.id != null && item.nextAttemptAt <= Date.now())
        .sort((a, b) => a.createdAt - b.createdAt)

      for (const item of items) {
        if (!navigator.onLine) break
        const headers = { ...item.headers }
        const res = await fetch(item.path, {
          method: item.method,
          credentials: 'include',
          headers,
          body: item.body,
        }).catch(() => null)

        if (!res) {
          item.attempts += 1
          item.lastError = 'Network unavailable'
          item.nextAttemptAt = Date.now() + Math.min(60_000, PREPZA_OFFLINE_QUEUE_BASE_DELAY_MS * (2 ** Math.min(item.attempts, 5)))
          await updatePrepzaOfflineQueueItem(item)
          break
        }

        if (res.ok || (res.status >= 400 && res.status < 500 && res.status !== 408 && res.status !== 409 && res.status !== 429)) {
          // Success, or a non-retryable client error. Do not replay it forever.
          await deletePrepzaOfflineQueueItem(item.id as number)
          continue
        }

        item.attempts += 1
        item.lastError = `Request failed (${res.status})`
        if (item.attempts >= PREPZA_OFFLINE_QUEUE_MAX_ATTEMPTS) {
          // Keep the item as a durable failed record rather than silently losing it.
          item.nextAttemptAt = Number.MAX_SAFE_INTEGER
        } else {
          item.nextAttemptAt = Date.now() + Math.min(60_000, PREPZA_OFFLINE_QUEUE_BASE_DELAY_MS * (2 ** Math.min(item.attempts, 5)))
        }
        await updatePrepzaOfflineQueueItem(item)
      }
      prepzaOfflineQueueChanged()
    } finally {
      prepzaOfflineQueueFlushPromise = null
    }
  })()
  return prepzaOfflineQueueFlushPromise
}

function startPrepzaOfflineQueue(): void {
  try {
    window.addEventListener('online', () => { void flushPrepzaOfflineQueue() })
    void flushPrepzaOfflineQueue()
  } catch {}
}

''' 
text = text[:idx] + queue_code + text[idx:]

# Explicit opt-in: existing mutations are never silently converted into queued writes.
# Callers can opt in with X-Prepza-Offline-Queue: true once an endpoint is designed for offline replay.
old_api_start = """async function api<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const { headers: extraHeaders, ...restOptions } = options
  const method = String(restOptions.method || 'GET').toUpperCase()
  const cacheKey = path
  const canUseOfflineData = method === 'GET' && path.startsWith('/') && !path.startsWith('/socket.io/')

  try {"""
new_api_start = """async function api<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const { headers: extraHeaders, ...restOptions } = options
  const method = String(restOptions.method || 'GET').toUpperCase()
  const queueOffline = method !== 'GET' && String((extraHeaders as Record<string, string> | undefined)?.['X-Prepza-Offline-Queue'] || '').toLowerCase() === 'true'
  const cacheKey = path
  const canUseOfflineData = method === 'GET' && path.startsWith('/') && !path.startsWith('/socket.io/')

  try {"""
if old_api_start not in text:
    raise SystemExit('Offline sync queue failed: O2 api helper start was not found.')
text = text.replace(old_api_start, new_api_start, 1)

old_catch = """  } catch (error) {
    if (canUseOfflineData) {
      const cached = await readPrepzaOffline<T>(cacheKey)
      if (cached !== null) return cached
    }
    throw error
  }
}"""
new_catch = """  } catch (error) {
    if (canUseOfflineData) {
      const cached = await readPrepzaOffline<T>(cacheKey)
      if (cached !== null) return cached
    }
    if (queueOffline && (!navigator.onLine || error instanceof TypeError)) {
      const queueHeaders = { ...(extraHeaders as Record<string, string> | undefined), 'X-Prepza-Offline-Queue': 'true' }
      const queueId = await enqueuePrepzaOfflineMutation(path, { ...restOptions, headers: queueHeaders })
      if (queueId != null) {
        return { queued: true, queue_id: queueId } as T
      }
    }
    throw error
  }
}"""
if old_catch not in text:
    raise SystemExit('Offline sync queue failed: O2 api helper catch block was not found.')
text = text.replace(old_catch, new_catch, 1)

# Start the replay loop after the helper definitions have been created.
start_anchor = "async function clearPrepzaOfflineData(): Promise<void> {"
start_pos = text.find(start_anchor)
if start_pos < 0:
    raise SystemExit('Offline sync queue failed: startup anchor disappeared.')
# Place startup immediately before clear helper so it is executed during module evaluation.
text = text[:start_pos] + "startPrepzaOfflineQueue()\n\n" + text[start_pos:]

required = [
    MARKER,
    'async function enqueuePrepzaOfflineMutation',
    'async function flushPrepzaOfflineQueue',
    "window.addEventListener('online'",
    "X-Prepza-Offline-Queue",
]
missing = [marker for marker in required if marker not in text]
if missing:
    raise SystemExit('Offline sync queue verification failed: ' + ', '.join(missing))

APP.write_text(text, encoding='utf-8')
print('Offline sync queue foundation applied and verified.')
