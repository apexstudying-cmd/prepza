const KEY = 'prepza-offline-study-activity-v2'
const MAX_DAILY_SECONDS = 8 * 60 * 60

type ScreenEntry = { seconds: number; syncedSeconds: number; documentId: number; feature: string }
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

/**
 * Records time for one specific study surface. This is deliberately not a
 * global timer: each My Study / My Library study screen owns its own tracker.
 */
export function recordOfflineStudySeconds(documentId: number, feature: string, seconds: number) {
  if (!Number.isInteger(documentId) || documentId <= 0) return
  if (!Number.isFinite(seconds) || seconds <= 0) return

  const state = load()
  const key = screenKey(documentId, feature)
  const row = state.screens[key] || { seconds: 0, syncedSeconds: 0, documentId, feature }
  row.seconds = Math.min(MAX_DAILY_SECONDS, row.seconds + Math.floor(seconds))
  state.screens[key] = row
  save(state)
  notify()
}

/**
 * Starts a timer owned by exactly one study screen. Leaving that screen stops
 * its timer, so time spent elsewhere in Prepza is never counted as study time.
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

/** Returns time accumulated for one document + study feature. */
export function getOfflineStudyScreenSnapshot(documentId: number, feature = 'reading') {
  const state = load()
  const row = state.screens[screenKey(documentId, feature)]
  return {
    documentId,
    feature,
    seconds: Math.max(0, Number(row?.seconds) || 0),
    syncedSeconds: Math.max(0, Number(row?.syncedSeconds) || 0),
  }
}

export function getOfflineStudySnapshot() {
  const state = load()
  const screens = Object.values(state.screens || {})
  const totalSeconds = screens.reduce((sum, row) => sum + Math.max(0, Number(row.seconds) || 0), 0)
  const todaySeconds = totalSeconds
  const activeDates = todaySeconds > 0 ? [todayKey()] : []
  return { totalSeconds, todaySeconds, currentStreak: todaySeconds > 0 ? 1 : 0, activeDates }
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
  const entries = Object.values(state.screens)
    .map(row => ({
      date: todayKey(),
      seconds: Math.max(0, Math.floor(Number(row.seconds) || 0)),
      syncedSeconds: Math.max(0, Math.floor(Number(row.syncedSeconds) || 0)),
    }))
    .filter(row => row.seconds > row.syncedSeconds)
    .map(row => ({ date: row.date, seconds: Math.min(MAX_DAILY_SECONDS, row.seconds - row.syncedSeconds) }))

  if (!entries.length) return

  const byDate: Record<string, number> = {}
  for (const entry of entries) byDate[entry.date] = (byDate[entry.date] || 0) + entry.seconds

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
      body: JSON.stringify({ entries: Object.entries(byDate).map(([date, seconds]) => ({ date, seconds })) }),
    })
    if (!res.ok) return

    const accepted: Record<string, number> = (await res.json()).accepted_seconds_by_date || {}
    for (const row of Object.values(state.screens)) {
      const acceptedForDate = Math.max(0, Number(accepted[todayKey()]) || 0)
      if (acceptedForDate > 0) row.syncedSeconds = Math.min(row.seconds, row.syncedSeconds + acceptedForDate)
    }
    save(state)
    notify()
  } catch {}
}
