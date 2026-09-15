let installed = false
let startX: number | null = null
let startY: number | null = null
let activeSurface: HTMLElement | null = null
let indicator: HTMLElement | null = null
let pullDistance = 0
let armed = false
let refreshing = false
let tracking = false
let verticalIntent = false

const MAX_PULL = 112
const TRIGGER_DISTANCE = 72
const RESISTANCE = 0.52

function appContentFallback(): HTMLElement | null {
  const root = document.getElementById('root')
  const shell = root?.firstElementChild
  const content = shell?.firstElementChild
  return content instanceof HTMLElement ? content : shell instanceof HTMLElement ? shell : null
}

function findSurface(target: EventTarget | null): HTMLElement | null {
  let node = target instanceof HTMLElement ? target : null
  while (node && node !== document.body && node !== document.documentElement) {
    const style = getComputedStyle(node)
    const scrollable = (style.overflowY === 'auto' || style.overflowY === 'scroll') && node.scrollHeight > node.clientHeight + 2
    if (scrollable) return node
    node = node.parentElement
  }
  return appContentFallback()
}

function atTop(surface: HTMLElement): boolean {
  return surface.scrollTop <= 2
}

function ensureIndicator(): HTMLElement {
  if (indicator) return indicator
  indicator = document.createElement('div')
  indicator.setAttribute('aria-hidden', 'true')
  Object.assign(indicator.style, {
    position: 'fixed', top: '0', left: '50%', zIndex: '2147483000',
    transform: 'translate3d(-50%,-120%,0)', width: '42px', height: '42px',
    borderRadius: '999px', display: 'flex', alignItems: 'center', justifyContent: 'center',
    background: 'rgba(11,20,55,.96)', color: '#C9A84C', fontSize: '21px',
    boxShadow: '0 3px 14px rgba(0,0,0,.22)', pointerEvents: 'none',
    opacity: '0', transition: 'opacity 100ms ease', willChange: 'transform,opacity',
  })
  indicator.textContent = '↓'
  document.body.appendChild(indicator)
  return indicator
}

function paintPull(distance: number): void {
  const value = Math.max(0, Math.min(MAX_PULL, distance))
  pullDistance = value
  const progress = value / MAX_PULL
  const el = ensureIndicator()
  el.style.transform = `translate3d(-50%, ${-120 + progress * 170}%, 0)`
  el.style.opacity = String(Math.min(1, 0.15 + progress * 1.15))
  el.textContent = armed ? '↻' : '↓'

  if (activeSurface) {
    activeSurface.style.transition = 'none'
    activeSurface.style.transform = `translate3d(0,${value * 0.34}px,0)`
  }
}

function clearPull(): void {
  if (activeSurface) {
    activeSurface.style.transition = 'transform 180ms cubic-bezier(.22,.8,.22,1)'
    activeSurface.style.transform = ''
  }
  if (indicator) {
    indicator.style.transform = 'translate3d(-50%,-120%,0)'
    indicator.style.opacity = '0'
  }
  pullDistance = 0
  armed = false
  tracking = false
  verticalIntent = false
  startX = null
  startY = null
  activeSurface = null
}

function triggerRefresh(): void {
  if (refreshing) return
  refreshing = true
  const el = ensureIndicator()
  el.textContent = '↻'
  el.style.transform = 'translate3d(-50%, 20%, 0)'
  el.style.opacity = '1'
  if (activeSurface) {
    activeSurface.style.transition = 'transform 220ms cubic-bezier(.22,.8,.22,1)'
    activeSurface.style.transform = `translate3d(0,${TRIGGER_DISTANCE * 0.34}px,0)`
  }
  window.setTimeout(() => window.location.reload(), 180)
}

export function installGlobalPullRefresh(): void {
  if (installed || typeof document === 'undefined') return
  installed = true

  document.addEventListener('touchstart', event => {
    if (refreshing || event.touches.length !== 1) return
    const surface = findSurface(event.target)
    if (!surface || !atTop(surface)) return
    const target = event.target instanceof HTMLElement ? event.target : null
    if (target?.closest('input, textarea, select, button, [contenteditable="true"]')) return

    activeSurface = surface
    startX = event.touches[0]?.clientX ?? null
    startY = event.touches[0]?.clientY ?? null
    pullDistance = 0
    armed = false
    tracking = true
    verticalIntent = false
  }, { passive: true, capture: true })

  document.addEventListener('touchmove', event => {
    if (!tracking || refreshing || !activeSurface || startX == null || startY == null || event.touches.length !== 1) return
    if (!atTop(activeSurface)) { clearPull(); return }

    const currentX = event.touches[0]?.clientX ?? startX
    const currentY = event.touches[0]?.clientY ?? startY
    const dx = currentX - startX
    const dy = currentY - startY

    if (!verticalIntent) {
      if (dy < 5) return
      if (Math.abs(dx) > Math.abs(dy) * 0.85) { clearPull(); return }
      verticalIntent = true
    }
    if (dy <= 0) { clearPull(); return }

    event.preventDefault()
    const resisted = Math.min(MAX_PULL, Math.pow(dy, RESISTANCE) * 10.2)
    paintPull(resisted)
    armed = pullDistance >= TRIGGER_DISTANCE
  }, { passive: false, capture: true })

  document.addEventListener('touchend', () => {
    if (!tracking) return
    if (armed && !refreshing) triggerRefresh()
    else clearPull()
  }, { passive: true, capture: true })

  document.addEventListener('touchcancel', clearPull, { passive: true, capture: true })
  window.addEventListener('pagehide', clearPull)
}
