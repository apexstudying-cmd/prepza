const KEY_PREFIX = 'prepza-offline-study-activity-v4'
const USER_KEY = 'prepza-offline-user-id'
const MAX_DAILY_SECONDS = 12 * 60 * 60

type DayEntry = { seconds: number; syncedSeconds: number }
type ScreenEntry = { documentId: number; feature: string; days: Record<string, DayEntry> }
type ActivityState = { screens: Record<string, ScreenEntry>; serverBaselines: Record<string, number> }

function storageKey(): string {
  try { return `${KEY_PREFIX}:${localStorage.getItem(USER_KEY) || 'unknown'}` } catch { return `${KEY_PREFIX}:unknown` }
}
const PREPZA_TIMEZONE = 'Africa/Nairobi'
function todayKey(date = new Date()): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: PREPZA_TIMEZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(date)
  const values = Object.fromEntries(parts.map(part => [part.type, part.value]))
  return `${values.year}-${values.month}-${values.day}`
}
function screenKey(documentId: number, feature: string): string { return `${Number(documentId)}:${String(feature || 'reading')}` }
function load(): ActivityState {
  try {
    const parsed = JSON.parse(localStorage.getItem(storageKey()) || '{}')
    if (parsed && typeof parsed.screens === 'object') {
      return {
        screens: parsed.screens,
        serverBaselines: parsed.serverBaselines && typeof parsed.serverBaselines === 'object'
          ? parsed.serverBaselines
          : {},
      }
    }
  } catch {}
  return { screens: {}, serverBaselines: {} }
}
function save(state: ActivityState) { try { localStorage.setItem(storageKey(), JSON.stringify(state)) } catch {} }
function notify() { window.dispatchEvent(new CustomEvent('prepza:offline-study-activity-changed')) }

export function setOfflineStudyUserId(userId: number | string) {
  const normalized = Number(userId)
  if (!Number.isInteger(normalized) || normalized <= 0) return
  try { localStorage.setItem(USER_KEY, String(normalized)) } catch {}
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
  save(state); notify()
}

export function startOfflineStudyTracking(documentId: number, feature = 'reading'): () => void {
  if (!Number.isInteger(documentId) || documentId <= 0) return () => {}
  let last = performance.now()
  let visible = document.visibilityState === 'visible'
  let interactedAt = visible ? performance.now() : 0
  let active = visible
  let stopped = false
  let fractionalSeconds = 0
  // Study credit continues while the student is genuinely visible/active, but
  // two continuous minutes without an interaction ends the credited session.
  // A later interaction resumes credit immediately.
  const INTERACTION_WINDOW_MS = 2 * 60 * 1000
  const markInteraction = () => {
    if (stopped) return
    interactedAt = performance.now()
    active = visible
  }
  const tick = () => {
    if (stopped) return
    const now = performance.now()
    const genuinelyActive = visible && active && (now - interactedAt <= INTERACTION_WINDOW_MS)
    if (genuinelyActive) {
      fractionalSeconds += Math.min(30, Math.max(0, (now - last) / 1000))
      const wholeSeconds = Math.floor(fractionalSeconds)
      if (wholeSeconds > 0) {
        recordOfflineStudySeconds(documentId, feature, wholeSeconds)
        fractionalSeconds -= wholeSeconds
      }
    } else if (fractionalSeconds >= 1) {
      recordOfflineStudySeconds(documentId, feature, Math.floor(fractionalSeconds))
      fractionalSeconds %= 1
    }
    last = now
  }
  const onVisibility = () => {
    tick()
    visible = document.visibilityState === 'visible'
    active = visible
    interactedAt = visible ? performance.now() : 0
    last = performance.now()
  }
  const onInteraction = () => markInteraction()
  document.addEventListener('visibilitychange', onVisibility)
  window.addEventListener('pointerdown', onInteraction, { passive: true })
  window.addEventListener('keydown', onInteraction, { passive: true })
  window.addEventListener('touchstart', onInteraction, { passive: true })
  window.addEventListener('scroll', onInteraction, { passive: true })
  const interval = window.setInterval(tick, 5000)
  window.addEventListener('pagehide', tick)
  return () => {
    if (stopped) return
    tick()
    fractionalSeconds = 0
    stopped = true
    window.clearInterval(interval)
    document.removeEventListener('visibilitychange', onVisibility)
    window.removeEventListener('pointerdown', onInteraction)
    window.removeEventListener('keydown', onInteraction)
    window.removeEventListener('touchstart', onInteraction)
    window.removeEventListener('scroll', onInteraction)
    window.removeEventListener('pagehide', tick)
  }
}

export function getOfflineStudyScreenSnapshot(documentId: number, feature = 'reading') {
  const state = load(), row = state.screens[screenKey(documentId, feature)], day = row?.days?.[todayKey()]
  return { documentId, feature, seconds: Math.max(0, Number(day?.seconds) || 0), syncedSeconds: Math.max(0, Number(day?.syncedSeconds) || 0) }
}

export function getOfflineStudySnapshot() {
  const state = load(), today = todayKey(), screens = Object.values(state.screens || {})
  const todaySeconds = screens.reduce((sum, row) => sum + Math.max(0, Number(row.days?.[today]?.seconds) || 0), 0)
  const allSeconds = screens.reduce((sum, row) => sum + Object.values(row.days || {}).reduce((daySum, day) => daySum + Math.max(0, Number(day.seconds) || 0), 0), 0)
  const activeDates = new Set<string>()
  for (const row of screens) for (const [date, day] of Object.entries(row.days || {})) if (Number(day.seconds) > 0) activeDates.add(date)
  let currentStreak = 0
  const cursor = new Date()
  for (;;) { const key = todayKey(cursor); if (!screens.some(row => Number(row.days?.[key]?.seconds) > 0)) break; currentStreak += 1; cursor.setDate(cursor.getDate() - 1) }
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
 * Sends absolute local daily totals. Server reconciliation is monotonic, so a
 * response lost after commit can safely be retried without double-counting.
 */
export async function syncOfflineStudyActivity(csrfToken?: string) {
  if (!navigator.onLine) return
  const state = load()
  const pending: Array<{ screen: ScreenEntry; date: string; totalSeconds: number; syncedSeconds: number }> = []
  const unsyncedByDate: Record<string, number> = {}

  for (const screen of Object.values(state.screens)) for (const [date, day] of Object.entries(screen.days || {})) {
    const totalSeconds = Math.min(MAX_DAILY_SECONDS, Math.max(0, Math.floor(Number(day.seconds) || 0)))
    const syncedSeconds = Math.min(totalSeconds, Math.max(0, Math.floor(Number(day.syncedSeconds) || 0)))
    if (totalSeconds > syncedSeconds) {
      pending.push({ screen, date, totalSeconds, syncedSeconds })
      unsyncedByDate[date] = Math.min(MAX_DAILY_SECONDS, (unsyncedByDate[date] || 0) + (totalSeconds - syncedSeconds))
    }
  }
  if (!pending.length) return

  let token = csrfToken
  if (!token) {
    try {
      const res = await fetch('/me', { credentials: 'include', cache: 'no-store' })
      if (!res.ok) return
      token = (await res.json()).csrf_token
    } catch { return }
  }

  // Establish a per-date server baseline before sending any local offline
  // delta. This preserves study time that existed before the device went
  // offline and makes the absolute target replay-safe after a lost response.
  const missingBaselineDates = Object.keys(unsyncedByDate).filter(date => !Number.isFinite(state.serverBaselines?.[date]))
  if (missingBaselineDates.length) {
    try {
      const baselineResponse = await fetch(`/study-time/offline-baselines?dates=${encodeURIComponent(missingBaselineDates.join(','))}`, {
        credentials: 'include',
        headers: token ? { 'X-CSRF-Token': token } : {},
      })
      if (!baselineResponse.ok) return
      const baselineBody = await baselineResponse.json()
      const serverTotals = baselineBody.server_total_seconds_by_date || {}
      for (const date of missingBaselineDates) {
        const serverTotal = Math.min(MAX_DAILY_SECONDS, Math.max(0, Number(serverTotals[date]) || 0))
        const alreadySynced = Math.min(
          unsyncedByDate[date] || 0,
          Object.values(state.screens)
            .filter(screen => screen.days?.[date])
            .reduce((sum, screen) => sum + Math.max(0, Number(screen.days[date].syncedSeconds) || 0), 0),
        )
        state.serverBaselines[date] = Math.max(0, serverTotal - alreadySynced)
      }
    } catch { return }
  }
  save(state)

  const entries = Object.entries(unsyncedByDate).map(([date, delta]) => ({
    date,
    total_seconds: Math.min(MAX_DAILY_SECONDS, Math.max(0, (state.serverBaselines[date] || 0) + delta)),
  }))

  try {
    const res = await fetch('/study-time/offline-sync', {
      method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': token || '' },
      body: JSON.stringify({ entries }),
    })
    if (!res.ok) return
    const body = await res.json()
    const serverTotals: Record<string, number> = body.server_total_seconds_by_date || {}
    const acceptedByDate: Record<string, number> = body.accepted_seconds_by_date || {}

    for (const date of Object.keys(unsyncedByDate)) {
      const serverTotal = Math.min(MAX_DAILY_SECONDS, Math.max(0, Number(serverTotals[date]) || 0))
      const baseline = Math.max(0, Number(state.serverBaselines[date]) || 0)
      const unsynced = Math.max(0, Number(unsyncedByDate[date]) || 0)
      const target = Math.min(MAX_DAILY_SECONDS, baseline + unsynced)

      if (serverTotal > target) {
        // Another server-side study source advanced this date while the
        // device was offline. Move the baseline forward but keep the local
        // unsynced delta intact so it is still credited on the next pass.
        state.serverBaselines[date] = serverTotal
        continue
      }

      let credited = Math.min(unsynced, Math.max(0, Number(acceptedByDate[date]) || 0))
      // If the server already equals our exact absolute target but reports
      // zero accepted seconds, the previous identical request likely
      // committed before its response was lost. Mark the local delta synced
      // rather than replaying it into a second increment.
      if (credited === 0 && serverTotal === target) credited = unsynced
      if (credited <= 0) continue

      let remaining = credited
      for (const item of pending) {
        if (item.date !== date || remaining <= 0) continue
        const day = item.screen.days[date]
        if (!day) continue
        const localUnsynced = Math.max(0, day.seconds - day.syncedSeconds)
        const applied = Math.min(localUnsynced, remaining)
        day.syncedSeconds += applied
        remaining -= applied
      }
    }
    save(state); notify()
  } catch {}
}
