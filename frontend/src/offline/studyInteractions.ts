const USER_KEY = 'prepza-offline-user-id'
const PREFIX = 'prepza-offline-study-interactions-v1'

type Interaction = {
  id: string
  documentId: number
  materialId?: number | null
  kind: 'flashcard' | 'quiz'
  index: number
  value: string
  correct?: boolean
  at: number
}

type Session = {
  documentId: number
  materialId?: number | null
  kind: 'flashcard' | 'quiz'
  index: number
  score: number
  completed: boolean
  updatedAt: number
}

function userId(): string { try { return localStorage.getItem(USER_KEY) || 'unknown' } catch { return 'unknown' } }
function key(kind: string, documentId: number, materialId?: number | null) { return `${PREFIX}:${userId()}:${kind}:${documentId}:${materialId ?? 'none'}` }
function loadSession(k: string): Session | null { try { const value = JSON.parse(localStorage.getItem(k) || 'null'); return value && typeof value === 'object' ? value : null } catch { return null } }
function saveSession(session: Session, k: string) { try { localStorage.setItem(k, JSON.stringify(session)) } catch {} }

export function recordOfflineStudyInteraction(input: Omit<Interaction, 'id' | 'at'>): void {
  const interaction: Interaction = { ...input, id: `${Date.now()}-${Math.random().toString(36).slice(2)}`, at: Date.now() }
  const k = `${PREFIX}:events:${userId()}`
  try {
    const rows = JSON.parse(localStorage.getItem(k) || '[]')
    const next = Array.isArray(rows) ? rows : []
    next.push(interaction)
    if (next.length > 500) next.splice(0, next.length - 500)
    localStorage.setItem(k, JSON.stringify(next))
  } catch {}
}

export function saveOfflineStudySession(session: Session): void { saveSession(session, key(session.kind, session.documentId, session.materialId)) }
export function getOfflineStudySession(documentId: number, kind: 'flashcard' | 'quiz', materialId?: number | null): Session | null { return loadSession(key(kind, documentId, materialId)) }
export function clearOfflineStudySession(documentId: number, kind: 'flashcard' | 'quiz', materialId?: number | null): void { try { localStorage.removeItem(key(kind, documentId, materialId)) } catch {} }

export function getOfflineStudyInteractions(): Interaction[] {
  try {
    const rows = JSON.parse(localStorage.getItem(`${PREFIX}:events:${userId()}`) || '[]')
    return Array.isArray(rows) ? rows : []
  } catch { return [] }
}
