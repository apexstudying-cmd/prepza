const DB_NAME = 'prepza-offline-chat-v1'
const STORE = 'messages'
const USER_KEY = 'prepza-offline-user-id'
const MAX_ATTEMPTS = 8
const BASE_DELAY_MS = 2000
const RETRY_TICK_MS = 5000

type QueuedChatMessage = {
  id?: number
  userId: number
  path: string
  method: 'POST'
  headers: Record<string, string>
  body: string
  createdAt: number
  attempts: number
  nextAttemptAt: number
  lastError: string | null
}

function currentUserId(): number | null {
  try {
    const id = Number(localStorage.getItem(USER_KEY) || 0)
    return Number.isInteger(id) && id > 0 ? id : null
  } catch { return null }
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1)
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(STORE)) {
        const store = db.createObjectStore(STORE, { keyPath: 'id', autoIncrement: true })
        store.createIndex('createdAt', 'createdAt', { unique: false })
        store.createIndex('userId', 'userId', { unique: false })
      }
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error || new Error('Offline chat storage is unavailable.'))
  })
}

export function isOfflineChatMessagePath(path: string): boolean {
  return /^\/chats\/\d+\/messages$/.test(path)
}

export async function enqueueOfflineChatMessage(path: string, body: string, csrfToken = ''): Promise<boolean> {
  const userId = currentUserId()
  if (!userId || !isOfflineChatMessagePath(path) || !body) return false
  const db = await openDb()
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite')
      tx.objectStore(STORE).add({
        userId,
        path,
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}),
        },
        body,
        createdAt: Date.now(),
        attempts: 0,
        nextAttemptAt: Date.now(),
        lastError: null,
      } satisfies QueuedChatMessage)
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error || new Error('Could not queue this message.'))
      tx.onabort = () => reject(tx.error || new Error('Could not queue this message.'))
    })
    window.dispatchEvent(new CustomEvent('prepza:offline-chat-queued', { detail: { path, body } }))
    return true
  } finally { db.close() }
}

async function readQueue(): Promise<QueuedChatMessage[]> {
  const userId = currentUserId()
  if (!userId) return []
  const db = await openDb()
  try {
    return await new Promise<QueuedChatMessage[]>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readonly')
      const request = tx.objectStore(STORE).getAll()
      request.onsuccess = () => resolve((request.result as QueuedChatMessage[]).filter(item => item.userId === userId).sort((a, b) => a.createdAt - b.createdAt))
      request.onerror = () => reject(request.error)
    })
  } finally { db.close() }
}

async function remove(id: number): Promise<void> {
  const db = await openDb()
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite')
      tx.objectStore(STORE).delete(id)
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
    })
  } finally { db.close() }
}

async function update(item: QueuedChatMessage): Promise<void> {
  if (item.id == null) return
  const db = await openDb()
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite')
      tx.objectStore(STORE).put(item)
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
    })
  } finally { db.close() }
}

let flushPromise: Promise<void> | null = null
let retryTimer: number | null = null

export async function flushOfflineChatMessages(): Promise<void> {
  if (!navigator.onLine || flushPromise) return flushPromise || Promise.resolve()
  flushPromise = (async () => {
    try {
      const queue = await readQueue()
      if (!queue.length) return
      const currentUser = currentUserId()
      if (!currentUser) return

      let csrf = ''
      try {
        const me = await fetch('/me', { credentials: 'include', cache: 'no-store' })
        if (!me.ok) return
        const meBody = await me.json()
        const serverUserId = Number(meBody?.id || 0)
        if (serverUserId !== currentUser) return
        csrf = String(meBody?.csrf_token || '')
      } catch { return }

      let changed = false
      for (const item of queue) {
        if (!navigator.onLine || item.userId !== currentUser) break
        if (item.nextAttemptAt > Date.now()) continue
        const headers = { ...item.headers }
        if (csrf) headers['X-CSRF-Token'] = csrf
        try {
          const response = await fetch(item.path, {
            method: item.method,
            credentials: 'include',
            headers,
            body: item.body,
          })
          if (response.ok || (response.status >= 400 && response.status < 500 && response.status !== 408 && response.status !== 409 && response.status !== 429)) {
            await remove(item.id as number)
            changed = true
            continue
          }
          throw new Error(`Request failed (${response.status})`)
        } catch (error) {
          item.attempts += 1
          item.lastError = error instanceof Error ? error.message : 'Message sync failed'
          item.nextAttemptAt = item.attempts >= MAX_ATTEMPTS
            ? Number.MAX_SAFE_INTEGER
            : Date.now() + Math.min(60_000, BASE_DELAY_MS * (2 ** Math.min(item.attempts, 5)))
          await update(item)
          changed = true
        }
      }
      if (changed) window.dispatchEvent(new CustomEvent('prepza:offline-chat-synced'))
    } finally { flushPromise = null }
  })()
  return flushPromise
}

export function installOfflineChatQueue(): void {
  if (typeof window === 'undefined') return
  window.addEventListener('online', () => { void flushOfflineChatMessages() })
  if (retryTimer == null) retryTimer = window.setInterval(() => { if (navigator.onLine) void flushOfflineChatMessages() }, RETRY_TICK_MS)
  void flushOfflineChatMessages()
}
