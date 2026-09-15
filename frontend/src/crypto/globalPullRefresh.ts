let installed = false
let startX: number | null = null
let startY: number | null = null
let activeSurface: HTMLElement | null = null
let indicator: HTMLElement | null = null
let pullDistance = 0
let armed = false
let refreshing = false

const MAX_PULL = 116
const TRIGGER_DISTANCE = 72

function findSurface(target: EventTarget | null): HTMLElement | null {
  let node = target instanceof HTMLElement ? target : null
  while (node && node !== document.body) {
    const style = getComputedStyle(node)
    if ((style.overflowY === 'auto' || style.overflowY === 'scroll') && node.scrollHeight > node.clientHeight + 2) return node
    node = node.parentElement
  }
  return document.scrollingElement as HTMLElement | null
}

function ensureIndicator(): HTMLElement {
  if (indicator) return indicator
  indicator = document.createElement('div')
  indicator.setAttribute('aria-hidden', 'true')
  indicator.style.cssText = [
    'position:fixed', 'top:0', 'left:50%', 'z-index:2147483000',
    'transform:translate(-50%,-100%)', 'width:42px', 'height:42px',
    'border-radius:999px', 'display:flex', 'align-items:center', 'justify-content:center',
    'background:rgba(11,20,55,.96)', 'color:#C9A84C', 'font-size:22px',
    'box-shadow:0 3px 14px rgba(0,0,0,.22)', 'pointer-events:none',
    'transition:transform 120ms ease, opacity 120ms ease', 'opacity:0',
  ].join(';')
  indicator.textContent = '↓'
  document.body.appendChild(indicator)
  return indicator
}

function paintPull(distance: number): void {
  const value = Math.max(0, Math.min(MAX_PULL, distance))
  pullDistance = value
  const el = ensureIndicator()
  const progress = value / MAX_PULL
  el.style.transform = `translate(-50%, ${-100 + progress * 190}%)`
  el.style.opacity = String(Math.min(1, progress * 1.8))
  el.textContent = armed ? '↻' : '↓'
  if (activeSurface) {
    activeSurface.style.transform = value > 0 ? `translateY(${value * 0.32}px)` : ''
    activeSurface.style.transition = 'none'
  }
}

function clearPull(): void {
  if (activeSurface) {
    activeSurface.style.transition = 'transform 180ms ease'
    activeSurface.style.transform = ''
  }
  if (indicator) {
    indicator.style.transform = 'translate(-50%,-100%)'
    indicator.style.opacity = '0'
  }
  pullDistance = 0
  armed = false
  startX = null
  startY = null
  activeSurface = null
}

function triggerRefresh(): void {
  if (refreshing) return
  refreshing = true
  const el = ensureIndicator()
  el.textContent = '↻'
  el.style.transform = 'translate(-50%, 20%)'
  el.style.opacity = '1'
  window.setTimeout(() => window.location.reload(), 120)
}

export function installGlobalPullRefresh(): void {
  if (installed || typeof document === 'undefined') return
  installed = true

  document.addEventListener('touchstart', event => {
    if (event.touches.length !== 1) return
    const surface = findSurface(event.target)
    if (!surface || surface.scrollTop > 2) return
    activeSurface = surface
    startX = event.touches[0]?.clientX ?? null
    startY = event.touches[0]?.clientY ?? null
    pullDistance = 0
    armed = false
  }, { passive: true, capture: true })

  document.addEventListener('touchmove', event => {
    if (startX == null || startY == null || !activeSurface || refreshing || event.touches.length !== 1) return
    if (activeSurface.scrollTop > 2) return
    const currentX = event.touches[0]?.clientX ?? startX
    const currentY = event.touches[0]?.clientY ?? startY
    const dx = currentX - startX
    const dy = currentY - startY
    if (dy <= 0 || dy <= Math.abs(dx) * 1.25) return
    const resisted = Math.sqrt(dy) * 8.5
    paintPull(Math.min(MAX_PULL, resisted))
    armed = pullDistance >= TRIGGER_DISTANCE
  }, { passive: true, capture: true })

  document.addEventListener('touchend', () => {
    if (armed && !refreshing) triggerRefresh()
    else clearPull()
  }, { passive: true, capture: true })
  document.addEventListener('touchcancel', clearPull, { passive: true, capture: true })

  window.addEventListener('pagehide', clearPull)
}
