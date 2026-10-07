const KEY_PREFIX = 'prepza-study-hub-activity-v1'
const USER_KEY = 'prepza-offline-user-id'
const MAX_DAILY_SECONDS = 12 * 60 * 60
const FLUSH_INTERVAL_MS = 60 * 60 * 1000
const INACTIVITY_WINDOW_MS = 2 * 60 * 1000
const PREPZA_TIMEZONE = 'Africa/Nairobi'

type DayEntry = { seconds: number; syncedSeconds: number }
type State = { days: Record<string, DayEntry> }

let installed = false
let active = false
let lastTick = 0
let interactedAt = 0
let fractionalSeconds = 0
let flushTimer: number | null = null
let tickTimer: number | null = null
let csrfToken: string | null = null
let syncing = false

function storageKey() {
  try { return `${KEY_PREFIX}:${localStorage.getItem(USER_KEY) || 'unknown'}` } catch { return `${KEY_PREFIX}:unknown` }
}

function todayKey(date = new Date()) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: PREPZA_TIMEZONE, year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(date)
  const values = Object.fromEntries(parts.map(p => [p.type, p.value]))
  return `${values.year}-${values.month}-${values.day}`
}

function load(): State {
  try {
    const parsed = JSON.parse(localStorage.getItem(storageKey()) || '{}')
    if (parsed && parsed.days && typeof parsed.days === 'object') return parsed
    // Migrate the previous per-document/per-feature local accumulator once.
    if (parsed && parsed.screens && typeof parsed.screens === 'object') {
      const days: Record<string, DayEntry> = {}
      for (const screen of Object.values<any>(parsed.screens)) {
        for (const [date, raw] of Object.entries<any>((screen as any).days || {})) {
          const day = days[date] || { seconds: 0, syncedSeconds: 0 }
          day.seconds = Math.min(MAX_DAILY_SECONDS, day.seconds + Math.max(0, Number((raw as any)?.seconds) || 0))
          day.syncedSeconds = Math.min(day.seconds, day.syncedSeconds + Math.max(0, Number((raw as any)?.syncedSeconds) || 0))
          days[date] = day
        }
      }
      return { days }
    }
  } catch {}
  return { days: {} }
}

function save(state: State) {
  try { localStorage.setItem(storageKey(), JSON.stringify(state)) } catch {}
}

function notify() {
  window.dispatchEvent(new CustomEvent('prepza:offline-study-activity-changed'))
}

export function setStudyHubUserId(userId: number | string) {
  const normalized = Number(userId)
  if (!Number.isInteger(normalized) || normalized <= 0) return
  try { localStorage.setItem(USER_KEY, String(normalized)) } catch {}
}

async function getCsrf(): Promise<string | null> {
  if (csrfToken) return csrfToken
  try {
    const response = await fetch('/me', { credentials: 'include', cache: 'no-store' })
    if (!response.ok) return null
    const body = await response.json()
    csrfToken = typeof body.csrf_token === 'string' ? body.csrf_token : null
    return csrfToken
  } catch { return null }
}

function tick() {
  if (!installed) return
  const now = performance.now()
  if (!lastTick) { lastTick = now; return }
  const elapsed = Math.max(0, Math.min(30, (now - lastTick) / 1000))
  const genuinelyActive = active && document.visibilityState === 'visible' && (now - interactedAt <= INACTIVITY_WINDOW_MS)
  if (genuinelyActive) {
    fractionalSeconds += elapsed
    const whole = Math.floor(fractionalSeconds)
    if (whole > 0) {
      const state = load()
      const date = todayKey()
      const day = state.days[date] || { seconds: 0, syncedSeconds: 0 }
      day.seconds = Math.min(MAX_DAILY_SECONDS, day.seconds + whole)
      state.days[date] = day
      save(state)
      notify()
      fractionalSeconds -= whole
    }
  }
  lastTick = now
}

async function flush() {
  if (syncing || !navigator.onLine) return
  tick()
  const state = load()
  const date = todayKey()
  const day = state.days[date]
  if (!day) return
  const totalSeconds = Math.min(MAX_DAILY_SECONDS, Math.max(0, Math.floor(day.seconds)))
  const syncedSeconds = Math.min(totalSeconds, Math.max(0, Math.floor(day.syncedSeconds)))
  if (totalSeconds <= syncedSeconds) return

  const token = await getCsrf()
  if (!token) return

  syncing = true
  try {
    const response = await fetch('/study-time/sync', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': token },
      body: JSON.stringify({ total_seconds: totalSeconds }),
    })
    if (!response.ok) return
    const body = await response.json()
    const serverTotal = Math.min(MAX_DAILY_SECONDS, Math.max(0, Number(body.total_seconds) || 0))
    // If the server already reached our exact target, this can be a retry
    // after a lost response. Mark the local target synchronized without
    // adding it again.
    day.syncedSeconds = Math.max(day.syncedSeconds, Math.min(day.seconds, serverTotal))
    state.days[date] = day
    save(state)
    notify()
  } catch {} finally {
    syncing = false
  }
}

export function setStudyHubActive(value: boolean) {
  tick()
  active = value
  lastTick = performance.now()
  interactedAt = active ? lastTick : 0
  void flush()
}

export function installStudyHubActivityTracker() {
  if (installed) return
  installed = true
  lastTick = performance.now()
  interactedAt = lastTick

  const markInteraction = () => {
    if (!installed) return
    tick()
    if (active && document.visibilityState === 'visible') interactedAt = performance.now()
  }
  const onVisibility = () => {
    // Visibility pauses crediting through genuinelyActive; it must not clear
    // the route-level active state. Otherwise returning to a visible tab would
    // leave the Study Hub clock permanently disabled until navigation occurs.
    tick()
    lastTick = performance.now()
    if (active && document.visibilityState === 'visible') interactedAt = lastTick
    void flush()
  }
  const onPageHide = () => { tick(); void flush() }

  document.addEventListener('visibilitychange', onVisibility)
  window.addEventListener('pointerdown', markInteraction, { passive: true })
  window.addEventListener('keydown', markInteraction, { passive: true })
  window.addEventListener('touchstart', markInteraction, { passive: true })
  window.addEventListener('scroll', markInteraction, { passive: true })
  window.addEventListener('pagehide', onPageHide)

  tickTimer = window.setInterval(tick, 5000)
  flushTimer = window.setInterval(() => void flush(), FLUSH_INTERVAL_MS)
  window.addEventListener('online', () => void flush())
}

export function getStudyHubSnapshot() {
  const state = load()
  const today = todayKey()
  const todaySeconds = Math.max(0, Number(state.days[today]?.seconds) || 0)
  const totalSeconds = Object.values(state.days).reduce((sum, day) => sum + Math.max(0, Number(day.seconds) || 0), 0)
  const activeDates = Object.entries(state.days).filter(([, day]) => Number(day.seconds) > 0).map(([date]) => date)
  return { totalSeconds, todaySeconds, activeDates }
}

// Compatibility exports for existing callers/tests. They now feed one global
// Study Hub clock rather than creating per-document clocks.
export function setOfflineStudyUserId(userId: number | string) { setStudyHubUserId(userId) }

export function recordOfflineStudySeconds(_documentId: number, _feature: string, seconds: number) {
  if (!Number.isFinite(seconds) || seconds <= 0) return
  const state = load()
  const date = todayKey()
  const day = state.days[date] || { seconds: 0, syncedSeconds: 0 }
  day.seconds = Math.min(MAX_DAILY_SECONDS, day.seconds + Math.floor(seconds))
  state.days[date] = day
  save(state)
  notify()
}

export function startOfflineStudyTracking(_documentId: number, _feature = 'reading') {
  setStudyHubActive(true)
  return () => setStudyHubActive(false)
}

export function getOfflineStudyScreenSnapshot(documentId: number, feature = 'reading') {
  const snap = getStudyHubSnapshot()
  return { documentId, feature, seconds: snap.todaySeconds, syncedSeconds: snap.todaySeconds }
}

export function getOfflineStudySnapshot() {
  const snap = getStudyHubSnapshot()
  let currentStreak = 0
  const cursor = new Date()
  const state = load()
  for (;;) {
    const key = todayKey(cursor)
    if (!(Number(state.days[key]?.seconds) > 0)) break
    currentStreak += 1
    cursor.setDate(cursor.getDate() - 1)
  }
  return { ...snap, currentStreak }
}

export async function syncOfflineStudyActivity(csrf?: string) {
  if (csrf) csrfToken = csrf
  await flush()
}
