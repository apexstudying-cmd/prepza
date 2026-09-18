let coreActions = 0
let visibleSince = 0
let lastHeartbeatAt = 0
let sessionStarted = false
let started = false
let timer: number | null = null

export function recordPrepzaCoreAction() {
  coreActions = Math.min(20, coreActions + 1)
}

async function csrfToken(): Promise<string | null> {
  try {
    const response = await fetch('/me', { credentials: 'include' })
    if (!response.ok) return null
    const body = await response.json()
    return typeof body?.csrf_token === 'string' ? body.csrf_token : null
  } catch {
    return null
  }
}

async function sendHeartbeat(force = false) {
  if (document.visibilityState !== 'visible') return
  const now = Date.now()
  if (!visibleSince) visibleSince = now
  if (!force && lastHeartbeatAt && now - lastHeartbeatAt < 15000) return

  const csrf = await csrfToken()
  if (!csrf) return

  const elapsedSeconds = Math.max(
    0,
    Math.min(120, Math.round((now - (lastHeartbeatAt || visibleSince)) / 1000)),
  )
  const isNewSession = !sessionStarted || now - lastHeartbeatAt > 30 * 60 * 1000

  try {
    const response = await fetch('/api/analytics/heartbeat', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrf,
      },
      body: JSON.stringify({
        engagement_seconds: elapsedSeconds,
        core_actions: coreActions,
        session_start: isNewSession,
      }),
      keepalive: true,
    })
    if (!response.ok) return
    sessionStarted = true
    lastHeartbeatAt = now
    coreActions = 0
  } catch {
    // Analytics must never interfere with the product.
  }
}

export function installActivityHeartbeat() {
  if (started || typeof window === 'undefined') return
  started = true
  visibleSince = document.visibilityState === 'visible' ? Date.now() : 0

  const tick = () => { void sendHeartbeat() }
  timer = window.setInterval(tick, 60000)

  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      visibleSince = Date.now()
      void sendHeartbeat(true)
    } else {
      void sendHeartbeat(true)
      visibleSince = 0
    }
  })

  window.addEventListener('pagehide', () => { void sendHeartbeat(true) })
  if (document.visibilityState === 'visible') void sendHeartbeat(true)
}

export function stopActivityHeartbeat() {
  if (timer !== null) window.clearInterval(timer)
  timer = null
  started = false
}
