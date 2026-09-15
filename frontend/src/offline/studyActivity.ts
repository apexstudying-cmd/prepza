const KEY = 'prepza-offline-study-activity-v3'
const MAX_DAILY_SECONDS = 8 * 60 * 60

type DayEntry = { seconds: number; syncedSeconds: number }
type ScreenEntry = { documentId: number; feature: string; days: Record<string, DayEntry> }
type ActivityState = { screens: Record<string, ScreenEntry> }

function todayKey(date = new Date()): string {
  const y = date.getFullYear(), m = String(date.getMonth() + 1).padStart(2, '0'), d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

function screenKey(documentId: number, feature: string): string {
  return `${Number(documentId)}:${String(feature || 'reading')}`
}

function load(): ActivityState {
  try {
    const parsed = JSON.parse(localStorage.getItem(KEY) || '{}')
    if (parsed && typeof parsed.screens === 'object') return parsed
  } catch {}
  return { screens: {} }
}

function save(state: ActivityState) {
  try { localStorage.setItem(KEY, JSON.stringify(state)) } catch {}
}

function notify() {
  window.dispatchEvent(new CustomEvent('prepza:offline-study-activity-changed'))
}

/** Records time for exactly one My Study / My Library study surface. */
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

/**
 * Timer is mounted by the individual study screen and stops on unmount.
 * Navigation to another screen therefore cannot leak time into this screen.
 */
export function startOfflineStudyTracking(documentId: number, feature = 'reading'): () => void {
  if (!Number.isInteger(documentId) || documentId <= 0) return () => {}

  let last = performance.now()
  let active = document.visibilityState === 'visible'
  let stopped = false

  const tick = () => {
    if (stopped) return
    const now = performance.now()
    if (active) {
      const seconds = Math.min(30, Math.max(0, (now - last) / 1000))
      recordOfflineStudySeconds(documentId, feature, seconds)
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
    stopped = true
    window.clearInterval(interval)
    document.removeEventListener('visibilitychange', onVisibility)
    window.removeEventListener('pagehide', tick)
  }
}

/** Returns time for one exact document + study feature, today. */
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
  for (const row of screens) {
    for (const [date, day] of Object.entries(row.days || {})) if (Number(day.seconds) > 0) activeDates.add(date)
  }

  let currentStreak = 0
  const cursor = new Date()
  for (;;) {
    const key = todayKey(cursor)
    if (![...screens].some(row => Number(row.days?.[key]?.seconds) > 0)) break
    currentStreak += 1
    cursor.setDate(cursor.getDate() - 1)
  }

  return { totalSeconds: allSeconds, todaySeconds, currentStreak, activeDates: [...activeDates].sort() }
}

export function mergeOfflineStudyResponse(path: string, body: any) {
  if (!body || typeof body !== 'object') return body
  const snap = getOfflineStudySnapshot()
  if (path.startsWith('/study-time')) {
    return { ...body, total_seconds: Math.max(Number(body.total_seconds) || 0, snap.totalSeconds), offline_today_seconds: snap.todaySeconds }
  }
  if (path === '/gamification/summary') {
    return { ...body, current_streak: Math.max(Number(body.current_streak) || 0, snap.currentStreak), offline_study_seconds_today: snap.todaySeconds }
  }
  return body
}

export async function syncOfflineStudyActivity(csrfToken?: string) {
  if (!navigator.onLine) return
  const state = load()
  const pending: Array<{ screen: ScreenEntry; date: string; seconds: number }> = []

  for (const screen of Object.values(state.screens)) {
    for (const [date, day] of Object.entries(screen.days || {})) {
      const seconds = Math.max(0, Math.floor(Number(day.seconds) || 0))
      const synced = Math.max(0, Math.floor(Number(day.syncedSeconds) || 0))
      if (seconds > synced) pending.push({ screen, date, seconds: seconds - synced })
    }
  }
  if (!pending.length) return

  const byDate: Record<string, number> = {}
  for (const item of pending) byDate[item.date] = (byDate[item.date] || 0) + item.seconds

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
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': token || '' },
      body: JSON.stringify({ entries: Object.entries(byDate).map(([date, seconds]) => ({ date, seconds: Math.min(MAX_DAILY_SECONDS, seconds) })) }),
    })
    if (!res.ok) return

    const accepted: Record<string, number> = (await res.json()).accepted_seconds_by_date || {}

    // The existing server endpoint accepts daily totals, not screen IDs.
    // Allocate the server-accepted amount deterministically across the exact
    // screen/day records that produced it, preserving their local ownership.
    for (const [date, acceptedValue] of Object.entries(accepted)) {
      let remaining = Math.max(0, Number(acceptedValue) || 0)
      for (const item of pending) {
        if (remaining <= 0 || item.date !== date) continue
        const day = item.screen.days[date]
        if (!day) continue
        const unsynced = Math.max(0, day.seconds - day.syncedSeconds)
        const credited = Math.min(unsynced, remaining)
        day.syncedSeconds += credited
        remaining -= credited
      }
    }

    save(state)
    notify()
  } catch {}
}
