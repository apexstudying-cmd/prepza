const KEY_PREFIX = 'prepza-offline-study-activity-v4'
const USER_KEY = 'prepza-offline-user-id'
const MAX_DAILY_SECONDS = 8 * 60 * 60

type DayEntry = { seconds: number; syncedSeconds: number }
type ScreenEntry = { documentId: number; feature: string; days: Record<string, DayEntry> }
type ActivityState = { screens: Record<string, ScreenEntry> }

function storageKey(): string {
  try { return `${KEY_PREFIX}:${localStorage.getItem(USER_KEY) || 'unknown'}` } catch { return `${KEY_PREFIX}:unknown` }
}

function todayKey(date = new Date()): string {
  const y = date.getFullYear(), m = String(date.getMonth() + 1).padStart(2, '0'), d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

function screenKey(documentId: number, feature: string): string {
  return `${Number(documentId)}:${String(feature || 'reading')}`
}

function load(): ActivityState {
  try {
    const parsed = JSON.parse(localStorage.getItem(storageKey()) || '{}')
    if (parsed && typeof parsed.screens === 'object') return parsed
  } catch {}
  return { screens: {} }
}

function save(state: ActivityState) {
  try { localStorage.setItem(storageKey(), JSON.stringify(state)) } catch {}
}

function notify() { window.dispatchEvent(new CustomEvent('prepza:offline-study-activity-changed')) }

export function setOfflineStudyUserId(userId: number) {
  if (!Number.isInteger(userId) || userId <= 0) return
  try { localStorage.setItem(USER_KEY, String(userId)) } catch {}
}

export function recordOfflineStudySeconds(documentId: number, feature: string, seconds: number) {
  if (!Number.isInteger(documentId) || documentId <= 0) return
  if (!Number.isFinite(seconds) || seconds <= 0) return

  const state = load()
  const key = screenKey(documentId, feature)
  const row = state.screens[key] || { documentId, feature, days: {} }
  const date = todayKey()
  const day = row.days[date] || { seconds: 0, syncedSeconds: 0 }
  day.seconds = Math.min(MAX_DAILY_SECONDS, day.seconds + Math.floor(seconds))
  row.days[date] = day
  state.screens[key] = row
  save(state)
  notify()
}

export function startOfflineStudyTracking(documentId: number, feature = 'reading'): () => void {
  if (!Number.isInteger(documentId) || documentId <= 0) return () => {}

  let last = performance.now()
  let active = document.visibilityState === 'visible'
  let stopped = false
  let fractionalSeconds = 0

  const tick = () => {
    if (stopped) return
    const now = performance.now()
    if (active) {
      const seconds = Math.min(30, Math.max(0, (now - last) / 1000))
      fractionalSeconds += seconds
      const wholeSeconds = Math.floor(fractionalSeconds)
      if (wholeSeconds > 0) {
        recordOfflineStudySeconds(documentId, feature, wholeSeconds)
        fractionalSeconds -= wholeSeconds
      }
    }
    last = now
  }

  const onVisibility = () => {
    tick()
    active = document.visibilityState === 'visible'
    last = performance.now()
  }

  document.addEventListener('visibilitychange', onVisibility)
  const interval = window.setInterval(tick, 5000)
  window.addEventListener('pagehide', tick)

  return () => {
    if (stopped) return
    tick()
    if (fractionalSeconds >= 0.5) recordOfflineStudySeconds(documentId, feature, fractionalSeconds)
    fractionalSeconds = 0
    stopped = true
    window.clearInterval(interval)
    document.removeEventListener('visibilitychange', onVisibility)
    window.removeEventListener('pagehide', tick)
  }
}

export function getOfflineStudyScreenSnapshot(documentId: number, feature = 'reading') {
  const state = load()
  const row = state.screens[screenKey(documentId, feature)]
  const day = row?.days?.[todayKey()]
  return {
    documentId,
    feature,
    seconds: Math.max(0, Number(day?.seconds) || 0),
    syncedSeconds: Math.max(0, Number(day?.syncedSeconds) || 0),
  }
}

export function getOfflineStudySnapshot() {
  const state = load()
  const today = todayKey()
  const screens = Object.values(state.screens || {})
  const todaySeconds = screens.reduce((sum, row) => sum + Math.max(0, Number(row.days?.[today]?.seconds) || 0), 0)
  const allSeconds = screens.reduce((sum, row) => sum + Object.values(row.days || {}).reduce((daySum, day) => daySum + Math.max(0, Number(day.seconds) || 0), 0), 0)
  const activeDates = new Set<string>()
  for (const row of screens) for (const [date, day] of Object.entries(row.days || {})) if (Number(day.seconds) > 0) activeDates.add(date)

  let currentStreak = 0
  const cursor = new Date()
  for (;;) {
    const key = todayKey(cursor)
    if (!screens.some(row => Number(row.days?.[key]?.seconds) > 0)) break
    currentStreak += 1
    cursor.setDate(cursor.getDate() - 1)
  }

  return { totalSeconds: allSeconds, todaySeconds, currentStreak, activeDates: [...activeDates].sort() }
}

export function mergeOfflineStudyResponse(path: string, body: any) {
  if (!body || typeof body !== 'object') return body
  const snap = getOfflineStudySnapshot()
  if (path.startsWith('/study-time')) return { ...body, total_seconds: Math.max(Number(body.total_seconds) || 0, snap.totalSeconds), offline_today_seconds: snap.todaySeconds }
  if (path === '/gamification/summary') return { ...body, current_streak: Math.max(Number(body.current_streak) || 0, snap.currentStreak), offline_study_seconds_today: snap.todaySeconds }
  return body
}

/**
 * Reconciles absolute local daily totals. Sending the same total repeatedly is
 * safe: the server only advances its authoritative total. This also lets the
 * client recover when a response was lost after the server committed it.
 */
export async function syncOfflineStudyActivity(csrfToken?: string) {
  if (!navigator.onLine) return
  const state = load()
  const pending: Array<{ screen: ScreenEntry; date: string; totalSeconds: number }> = []
  const byDate: Record<string, number> = {}

  for (const screen of Object.values(state.screens)) for (const [date, day] of Object.entries(screen.days || {})) {
    const totalSeconds = Math.min(MAX_DAILY_SECONDS, Math.max(0, Math.floor(Number(day.seconds) || 0)))
    const synced = Math.max(0, Math.floor(Number(day.syncedSeconds) || 0))
    if (totalSeconds > synced) {
      pending.push({ screen, date, totalSeconds })
      byDate[date] = Math.min(MAX_DAILY_SECONDS, (byDate[date] || 0) + (totalSeconds - synced))
    }
  }
  if (!pending.length) return

  // The server expects a target total. Reconstruct it from the local synced
  // baseline plus unsynced delta, while keeping the payload capped per day.
  const localSyncedByDate: Record<string, number> = {}
  for (const screen of Object.values(state.screens)) for (const [date, day] of Object.entries(screen.days || {})) {
    localSyncedByDate[date] = Math.max(localSyncedByDate[date] || 0, Math.max(0, Math.floor(Number(day.syncedSeconds) || 0)))
  }
  const entries = Object.entries(byDate).map(([date, delta]) => ({
    date,
    total_seconds: Math.min(MAX_DAILY_SECONDS, (localSyncedByDate[date] || 0) + delta),
  }))

  let token = csrfToken
  if (!token) {
    try {
      const res = await fetch('/me', { credentials: 'include', cache: 'no-store' })
      if (!res.ok) return
      token = (await res.json()).csrf_token
    } catch { return }
  }

  try {
    const res = await fetch('/study-time/offline-sync', {
      method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': token || '' },
      body: JSON.stringify({ entries }),
    })
    if (!res.ok) return
    const body = await res.json()
    const serverTotals: Record<string, number> = body.server_total_seconds_by_date || {}

    // Mark each local screen up to the authoritative server total. If another
    // device already has more time, the local unsynced delta is considered
    // reconciled rather than being replayed indefinitely.
    for (const item of pending) {
      const day = item.screen.days[item.date]
      if (!day) continue
      const authoritative = Math.max(0, Math.min(MAX_DAILY_SECONDS, Number(serverTotals[item.date]) || 0))
      day.syncedSeconds = Math.min(day.seconds, Math.max(day.syncedSeconds, authoritative))
    }
    save(state); notify()
  } catch {}
}
