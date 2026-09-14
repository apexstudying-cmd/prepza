let installed = false
let startX: number | null = null
let startY: number | null = null
let activeSurface: HTMLElement | null = null
let triggered = false

function findSurface(target: EventTarget | null): HTMLElement | null {
  let node = target instanceof HTMLElement ? target : null
  while (node && node !== document.body) {
    const style = getComputedStyle(node)
    if ((style.overflowY === 'auto' || style.overflowY === 'scroll') && node.scrollHeight > node.clientHeight + 2) return node
    node = node.parentElement
  }
  const root = document.scrollingElement
  return root && root.scrollHeight > root.clientHeight + 2 ? root as HTMLElement : null
}

function triggerRefresh() {
  if (triggered) return
  triggered = true
  // App persists its navigation stack and active IDs in sessionStorage, so a
  // real reload refreshes the current screen rather than routing to Home.
  window.location.reload()
}

export function installGlobalPullRefresh(): void {
  if (installed || typeof document === 'undefined') return
  installed = true

  // Covers every screen, including screens that don't contain chat messages.
  document.addEventListener('touchstart', event => {
    const surface = findSurface(event.target)
    if (!surface || surface.scrollTop > 2 || event.touches.length !== 1) return
    activeSurface = surface
    startX = event.touches[0]?.clientX ?? null
    startY = event.touches[0]?.clientY ?? null
    triggered = false
  }, { passive: true, capture: true })

  document.addEventListener('touchmove', event => {
    if (startX == null || startY == null || !activeSurface || triggered || activeSurface.scrollTop > 2 || event.touches.length !== 1) return
    const currentX = event.touches[0]?.clientX ?? startX
    const currentY = event.touches[0]?.clientY ?? startY
    const dx = currentX - startX
    const dy = currentY - startY
    // Only a genuinely downward gesture should refresh; horizontal swipes
    // belong to the primary navigation gesture.
    if (dy >= 72 && dy > Math.abs(dx) * 1.35) triggerRefresh()
  }, { passive: true, capture: true })

  const reset = () => { startX = null; startY = null; activeSurface = null; triggered = false }
  document.addEventListener('touchend', reset, { passive: true, capture: true })
  document.addEventListener('touchcancel', reset, { passive: true, capture: true })

  // The existing chat polish layer emits this event. Listening here makes its
  // pull gesture perform the same real refresh instead of a no-op event.
  window.addEventListener('prepza-realtime-message', event => {
    const detail = (event as CustomEvent).detail as { refresh?: boolean } | undefined
    if (detail?.refresh) triggerRefresh()
  })
}
