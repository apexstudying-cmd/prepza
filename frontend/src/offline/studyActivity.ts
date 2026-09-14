const KEY = 'prepza-offline-study-activity-v1'
const MAX_DAILY_SECONDS = 8 * 60 * 60

type DayEntry = { seconds: number; syncedSeconds: number }
type ActivityState = { days: Record<string, DayEntry> }

function todayKey(date = new Date()): string {
  const y = date.getFullYear(), m = String(date.getMonth() + 1).padStart(2, '0'), d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

function load(): ActivityState {
  try {
    const parsed = JSON.parse(localStorage.getItem(KEY) || '{}')
    return parsed && typeof parsed.days === 'object' ? parsed : { days: {} }
  } catch { return { days: {} } }
}

function save(state: ActivityState) {
  try { localStorage.setItem(KEY, JSON.stringify(state)) } catch {}
}

function notify() {
  window.dispatchEvent(new CustomEvent('prepza:offline-study-activity-changed'))
}

export function recordOfflineStudySeconds(seconds: number) {
  if (!Number.isFinite(seconds) || seconds <= 0) return
  const state = load(); const key = todayKey(); const row = state.days[key] || { seconds: 0, syncedSeconds: 0 }
  row.seconds = Math.min(MAX_DAILY_SECONDS, row.seconds + Math.floor(seconds))
  state.days[key] = row; save(state); notify()
}

export function startOfflineStudyTracking(documentId: number, feature = 'reading'): () => void {
  let last = performance.now(); let active = document.visibilityState === 'visible';
  const tick = () => {
    const now = performance.now()
    if (active) recordOfflineStudySeconds(Math.min(30, Math.max(0, (now - last) / 1000)))
    last = now
  }
  const onVisibility = () => { tick(); active = document.visibilityState === 'visible'; last = performance.now() }
  document.addEventListener('visibilitychange', onVisibility)
  const interval = window.setInterval(tick, 5000)
  window.addEventListener('pagehide', tick)
  return () => { tick(); window.clearInterval(interval); document.removeEventListener('visibilitychange', onVisibility); window.removeEventListener('pagehide', tick) }
}

export function getOfflineStudySnapshot() {
  const state = load(); const days = state.days || {}; const today = todayKey()
  const totalSeconds = Object.values(days).reduce((sum, row) => sum + Math.max(0, Number(row.seconds) || 0), 0)
  const todaySeconds = Math.max(0, Number(days[today]?.seconds) || 0)
  const activeDates = Object.keys(days).filter(key => (Number(days[key]?.seconds) || 0) > 0).sort()
  let currentStreak = 0
  const cursor = new Date()
  for (;;) {
    const key = todayKey(cursor); if (!(Number(days[key]?.seconds) > 0)) break
    currentStreak += 1; cursor.setDate(cursor.getDate() - 1)
  }
  return { totalSeconds, todaySeconds, currentStreak, activeDates }
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
  const state = load(); const entries = Object.entries(state.days)
    .map(([date, row]) => ({ date, seconds: Math.max(0, Math.floor(Number(row.seconds) || 0)), syncedSeconds: Math.max(0, Math.floor(Number(row.syncedSeconds) || 0)) }))
    .filter(row => row.seconds > row.syncedSeconds)
    .map(row => ({ date: row.date, seconds: Math.min(MAX_DAILY_SECONDS, row.seconds - row.syncedSeconds) }))
  if (!entries.length) return
  let token = csrfToken
  if (!token) {
    try { const res = await fetch('/me', { credentials: 'include', cache: 'no-store' }); if (!res.ok) return; token = (await res.json()).csrf_token } catch { return }
  }
  try {
    const res = await fetch('/study-time/offline-sync', { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': token || '' }, body: JSON.stringify({ entries }) })
    if (!res.ok) return
    const accepted: Record<string, number> = (await res.json()).accepted_seconds_by_date || {}
    for (const [date, seconds] of Object.entries(accepted)) {
      if (state.days[date]) state.days[date].syncedSeconds = Math.min(state.days[date].seconds, state.days[date].syncedSeconds + Math.max(0, Number(seconds) || 0))
    }
    save(state); notify()
  } catch {}
}
