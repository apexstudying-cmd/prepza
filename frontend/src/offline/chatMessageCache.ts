const DB_NAME = 'prepza-chat-cache-v1'
const STORE = 'conversations'
const MAX_MESSAGES_PER_CONVERSATION = 200
const MAX_CONVERSATIONS = 20
const MAX_TOTAL_BYTES = 8 * 1024 * 1024
const MAX_MESSAGE_BYTES = 64 * 1024
const RETENTION_MS = 30 * 24 * 60 * 60 * 1000

type CacheRow = {
  key: string
  userId: number
  conversationId: number
  messages: unknown[]
  bytes: number
  updatedAt: number
}

function currentUserId(): number | null {
  try {
    const id = Number(localStorage.getItem('prepza-offline-user-id') || 0)
    return Number.isInteger(id) && id > 0 ? id : null
  } catch { return null }
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1)
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(STORE)) {
        const store = db.createObjectStore(STORE, { keyPath: 'key' })
        store.createIndex('userId', 'userId', { unique: false })
        store.createIndex('updatedAt', 'updatedAt', { unique: false })
      }
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error || new Error('Chat cache unavailable'))
  })
}

function estimateBytes(messages: unknown[]): number {
  try { return new Blob([JSON.stringify(messages)]).size } catch { return 0 }
}

function pruneMessages(messages: unknown[]): unknown[] {
  const normalized = Array.isArray(messages) ? messages : []
  const bounded = normalized.slice(-MAX_MESSAGES_PER_CONVERSATION)
  return bounded.filter(message => {
    try { return JSON.stringify(message).length <= MAX_MESSAGE_BYTES } catch { return false }
  })
}

async function readRows(userId: number): Promise<CacheRow[]> {
  const db = await openDb()
  try {
    return await new Promise<CacheRow[]>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readonly')
      const req = tx.objectStore(STORE).getAll()
      req.onsuccess = () => resolve((req.result as CacheRow[]).filter(row => row.userId === userId))
      req.onerror = () => reject(req.error)
    })
  } finally { db.close() }
}

async function deleteKeys(keys: string[]): Promise<void> {
  if (!keys.length) return
  const db = await openDb()
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite')
      const store = tx.objectStore(STORE)
      keys.forEach(key => store.delete(key))
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
      tx.onabort = () => reject(tx.error)
    })
  } finally { db.close() }
}

async function putRow(row: CacheRow): Promise<void> {
  const db = await openDb()
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite')
      tx.objectStore(STORE).put(row)
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
      tx.onabort = () => reject(tx.error)
    })
  } finally { db.close() }
}

async function evictIfNeeded(userId: number, incomingBytes: number, incomingKey: string): Promise<void> {
  const rows = (await readRows(userId)).sort((a, b) => a.updatedAt - b.updatedAt)
  const stale = rows.filter(row => Date.now() - row.updatedAt > RETENTION_MS && row.key !== incomingKey)
  let candidates = stale.length ? stale : rows.filter(row => row.key !== incomingKey)

  let total = rows.reduce((sum, row) => sum + row.bytes, 0)
  const keys: string[] = []
  let conversationCount = rows.length

  while ((total + incomingBytes > MAX_TOTAL_BYTES || conversationCount >= MAX_CONVERSATIONS) && candidates.length) {
    const victim = candidates.shift()!
    total -= victim.bytes
    conversationCount -= 1
    keys.push(victim.key)
  }
  if (keys.length) await deleteKeys(keys)
}

export async function cacheChatMessages(conversationId: number, messages: unknown[]): Promise<void> {
  const userId = currentUserId()
  if (!userId || !Number.isInteger(conversationId) || conversationId <= 0) return
  const safeMessages = pruneMessages(messages)
  if (!safeMessages.length) return
  const bytes = estimateBytes(safeMessages)
  if (!bytes || bytes > MAX_TOTAL_BYTES) return
  const key = `${userId}:${conversationId}`
  try {
    await evictIfNeeded(userId, bytes, key)
    await putRow({ key, userId, conversationId, messages: safeMessages, bytes, updatedAt: Date.now() })
  } catch {
    // Cache is an optimization. Quota/private-mode/IndexedDB failures must
    // never make the chat itself fail.
  }
}

export async function getCachedChatMessages(conversationId: number): Promise<unknown[] | null> {
  const userId = currentUserId()
  if (!userId || !Number.isInteger(conversationId) || conversationId <= 0) return null
  try {
    const db = await openDb()
    try {
      const row = await new Promise<CacheRow | undefined>((resolve, reject) => {
        const tx = db.transaction(STORE, 'readonly')
        const req = tx.objectStore(STORE).get(`${userId}:${conversationId}`)
        req.onsuccess = () => resolve(req.result as CacheRow | undefined)
        req.onerror = () => reject(req.error)
      })
      if (!row) return null
      if (Date.now() - row.updatedAt > RETENTION_MS) {
        await deleteKeys([row.key])
        return null
      }
      return Array.isArray(row.messages) ? row.messages : null
    } finally { db.close() }
  } catch { return null }
}

export async function clearCachedChatMessages(conversationId: number): Promise<void> {
  const userId = currentUserId()
  if (!userId) return
  try { await deleteKeys([`${userId}:${conversationId}`]) } catch {}
}
