export type OfflineChatAction = {
  id: string
  userId: number
  conversationId: number
  body: string
  createdAt: number
  attempts: number
}

const QUEUE_KEY = 'prepza-chat-offline-queue-v1'
const MAX_QUEUE = 100

function read(): OfflineChatAction[] {
  try {
    const raw = localStorage.getItem(QUEUE_KEY)
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function write(items: OfflineChatAction[]): void {
  try { localStorage.setItem(QUEUE_KEY, JSON.stringify(items.slice(-MAX_QUEUE))) } catch {}
}

export function enqueueOfflineChatAction(action: Omit<OfflineChatAction, 'id' | 'createdAt' | 'attempts'>): OfflineChatAction {
  const item: OfflineChatAction = {
    ...action,
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    createdAt: Date.now(),
    attempts: 0,
  }
  const items = read()
  items.push(item)
  write(items)
  return item
}

export function getOfflineChatQueue(userId: number): OfflineChatAction[] {
  return read().filter(item => item.userId === userId)
}

export function removeOfflineChatActions(ids: string[]): void {
  if (!ids.length) return
  const remove = new Set(ids)
  write(read().filter(item => !remove.has(item.id)))
}

export function markOfflineChatActionAttempted(id: string): void {
  write(read().map(item => item.id === id ? { ...item, attempts: item.attempts + 1 } : item))
}

export function clearOfflineChatQueue(userId: number): void {
  write(read().filter(item => item.userId !== userId))
}
