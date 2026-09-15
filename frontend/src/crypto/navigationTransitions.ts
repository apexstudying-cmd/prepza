let installed = false
let lastKnownIndex: number | null = null
let swipePointerId: number | null = null
let swipeStartX: number | null = null
let swipeStartY: number | null = null
let swipeLastX: number | null = null
let swipeLastTime = 0
let swipeVelocityX = 0
let swipeDeltaX = 0
let swipeActive = false
let swipeAnimation: Animation | null = null
let swipeFrame: number | null = null
let navigationInProgress = false

const PRIMARY_NAV_LABELS = ['home', 'explore', 'chats', 'profile'] as const
const PRIMARY_SWIPE_SCREENS = new Set<string>(PRIMARY_NAV_LABELS)
const SWIPE_THRESHOLD = 56
const SWIPE_VELOCITY_THRESHOLD = 0.45
const SWIPE_ACTIVATION_DISTANCE = 8
const TRANSITION_DURATION = 240
const MOTION_EASE = 'cubic-bezier(.22,.8,.22,1)'
const COLOR_EASE = 'color 220ms cubic-bezier(.22,.8,.22,1)'
const NAVIGATION_STORAGE_KEY = 'prepza-navigation-state'

function currentAppScreen(): string | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = window.localStorage.getItem(NAVIGATION_STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as { stack?: unknown }
    if (!Array.isArray(parsed.stack) || parsed.stack.length === 0) return null
    const screen = parsed.stack[parsed.stack.length - 1]
    return typeof screen === 'string' ? screen : null
  } catch {
    return null
  }
}

function isPrimarySwipeScreen(): boolean {
  const screen = currentAppScreen()
  return screen !== null && PRIMARY_SWIPE_SCREENS.has(screen)
}

function navLabel(button: HTMLElement): string {
  return `${button.getAttribute('aria-label') || ''} ${button.getAttribute('title') || ''} ${button.textContent || ''}`.trim().toLowerCase()
}

function isPrimaryNavButton(button: HTMLElement): boolean {
  const label = navLabel(button)
  return Boolean(button.querySelector('svg')) && PRIMARY_NAV_LABELS.some(item => label === item || label.includes(item))
}

function primaryButtons(): HTMLButtonElement[] {
  const found = Array.from(document.querySelectorAll<HTMLButtonElement>('button')).filter(isPrimaryNavButton)
  return PRIMARY_NAV_LABELS.map(label => found.find(button => navLabel(button).includes(label)) || null).filter(Boolean) as HTMLButtonElement[]
}

function activeNavIndex(buttons: HTMLButtonElement[]): number {
  // Always prefer the DOM's current active state. lastKnownIndex is only a
  // fallback for the tiny render gap between a click and React committing it.
  const active = buttons.findIndex(button => {
    const className = typeof button.className === 'string' ? button.className : ''
    return button.getAttribute('aria-current') === 'page'
      || button.getAttribute('data-state') === 'active'
      || button.getAttribute('aria-pressed') === 'true'
      || button.querySelector('[aria-current="page"]') !== null
      || /(^|[\s_-])(active|selected|current)([\s_-]|$)/i.test(className)
  })
  if (active >= 0) {
    lastKnownIndex = active
    return active
  }
  if (lastKnownIndex != null && lastKnownIndex >= 0 && lastKnownIndex < buttons.length) return lastKnownIndex
  lastKnownIndex = 0
  return 0
}

function contentElement(): HTMLElement | null {
  const root = document.getElementById('root')
  const appShell = root?.firstElementChild
  const content = appShell?.firstElementChild
  return content instanceof HTMLElement ? content : null
}

function resetContentTransform(): void {
  const content = contentElement()
  if (!content) return
  content.style.transform = ''
  content.style.willChange = ''
}

function cancelSwipeAnimation(): void {
  swipeAnimation?.cancel()
  swipeAnimation = null
  if (swipeFrame != null) {
    cancelAnimationFrame(swipeFrame)
    swipeFrame = null
  }
}

function preparePagerSurface(): void {
  const content = contentElement()
  if (!content) return
  // Allow the browser to keep vertical scrolling native while this surface
  // owns horizontal paging. Pointer events then remain available for the
  // horizontal gesture instead of being lost to browser scrolling.
  content.style.touchAction = 'pan-y pinch-zoom'
  content.style.overscrollBehaviorX = 'none'
}

function prepareNavColorTransitions(): void {
  primaryButtons().forEach(button => {
    if (!button.style.transition.includes(COLOR_EASE)) {
      button.style.transition = button.style.transition ? `${button.style.transition}, ${COLOR_EASE}` : COLOR_EASE
    }
  })
}

function copyScrollPositions(source: Element, target: Element): void {
  if (source instanceof HTMLElement && target instanceof HTMLElement) {
    target.scrollTop = source.scrollTop
    target.scrollLeft = source.scrollLeft
  }
  Array.from(source.children).forEach((child, index) => {
    const targetChild = target.children[index]
    if (targetChild) copyScrollPositions(child, targetChild)
  })
}

function stripCloneIds(root: Element): void {
  if (root instanceof HTMLElement) root.removeAttribute('id')
  root.querySelectorAll('[id]').forEach(node => node.removeAttribute('id'))
}

function createOutgoingLayer(content: HTMLElement): HTMLElement | null {
  const rect = content.getBoundingClientRect()
  if (rect.width <= 0 || rect.height <= 0) return null
  const contentStyle = getComputedStyle(content)
  const root = document.getElementById('root')
  const appShell = root?.firstElementChild
  const rootBackground = root ? getComputedStyle(root).backgroundColor : 'transparent'
  const shellBackground = appShell instanceof HTMLElement ? getComputedStyle(appShell).backgroundColor : 'transparent'
  const background = contentStyle.backgroundColor !== 'rgba(0, 0, 0, 0)'
    ? contentStyle.backgroundColor
    : shellBackground !== 'rgba(0, 0, 0, 0)' ? shellBackground : rootBackground
  const host = document.createElement('div')
  host.setAttribute('aria-hidden', 'true')
  host.dataset.prepzaNavLayer = 'outgoing'
  Object.assign(host.style, {
    position: 'fixed', left: `${rect.left}px`, top: `${rect.top}px`,
    width: `${rect.width}px`, height: `${rect.height}px`, overflow: 'hidden',
    boxSizing: 'border-box', zIndex: '40', pointerEvents: 'none', background,
    transform: `translate3d(${swipeDeltaX}px,0,0)`, willChange: 'transform',
    backfaceVisibility: 'hidden', contain: 'paint',
  })
  const clone = content.cloneNode(true) as HTMLElement
  stripCloneIds(clone)
  Object.assign(clone.style, {
    position: 'absolute', left: '0', top: '0', width: `${content.offsetWidth}px`,
    minHeight: `${content.offsetHeight}px`, transform: 'none', overflow: contentStyle.overflow,
    background, pointerEvents: 'none', backfaceVisibility: 'hidden',
  })
  host.appendChild(clone)
  document.body.appendChild(host)
  copyScrollPositions(content, clone)
  return host
}

function animateBack(): void {
  const content = contentElement()
  if (!content) return
  cancelSwipeAnimation()
  const from = swipeDeltaX
  if (Math.abs(from) < 0.5) {
    resetContentTransform()
    return
  }
  swipeAnimation = content.animate(
    [{ transform: `translate3d(${from}px,0,0)` }, { transform: 'translate3d(0,0,0)' }],
    { duration: Math.min(220, Math.max(140, Math.round(Math.abs(from) * 0.8))), easing: MOTION_EASE, fill: 'forwards' },
  )
  swipeAnimation.onfinish = () => { swipeAnimation = null; resetContentTransform() }
}

function finishNavigation(direction: 'left' | 'right', navigate: () => void): void {
  if (navigationInProgress) return
  const content = contentElement()
  if (!content) { navigate(); return }
  navigationInProgress = true
  cancelSwipeAnimation()
  const outgoingLayer = createOutgoingLayer(content)
  const sign = direction === 'left' ? -1 : 1
  const width = Math.max(window.innerWidth, content.clientWidth || 0)
  content.style.visibility = 'hidden'
  content.style.transform = `translate3d(${-sign * width}px,0,0)`
  content.style.willChange = 'transform'
  navigate()
  requestAnimationFrame(() => {
    const nextContent = contentElement()
    if (!nextContent) {
      outgoingLayer?.remove()
      navigationInProgress = false
      resetContentTransform()
      return
    }
    nextContent.style.visibility = 'visible'
    nextContent.style.willChange = 'transform'
    nextContent.style.transform = `translate3d(${-sign * width}px,0,0)`
    const outgoingAnimation = outgoingLayer?.animate(
      [{ transform: `translate3d(${swipeDeltaX}px,0,0)` }, { transform: `translate3d(${sign * width}px,0,0)` }],
      { duration: TRANSITION_DURATION, easing: MOTION_EASE, fill: 'forwards' },
    )
    const incomingAnimation = nextContent.animate(
      [{ transform: `translate3d(${-sign * width}px,0,0)` }, { transform: 'translate3d(0,0,0)' }],
      { duration: TRANSITION_DURATION, easing: MOTION_EASE, fill: 'forwards' },
    )
    Promise.allSettled([outgoingAnimation?.finished, incomingAnimation.finished]).then(() => {
      outgoingLayer?.remove()
      nextContent.style.visibility = ''
      nextContent.style.willChange = ''
      nextContent.style.transform = ''
      navigationInProgress = false
    })
  })
}

function navigateBySwipe(direction: 'next' | 'previous'): void {
  const buttons = primaryButtons()
  if (buttons.length < 2) return
  const active = activeNavIndex(buttons)
  const nextIndex = direction === 'next' ? active + 1 : active - 1
  if (nextIndex < 0 || nextIndex >= buttons.length) { animateBack(); return }
  lastKnownIndex = nextIndex
  finishNavigation(direction === 'next' ? 'left' : 'right', () => buttons[nextIndex].click())
}

function isHorizontalScroller(target: EventTarget | null): boolean {
  const pager = contentElement()
  let node = target instanceof HTMLElement ? target : null
  while (node && node !== document.body) {
    if (node === pager) break
    const style = getComputedStyle(node)
    if ((style.overflowX === 'auto' || style.overflowX === 'scroll') && node.scrollWidth > node.clientWidth + 4) return true
    node = node.parentElement
  }
  return false
}

function resetSwipeState(): void {
  swipePointerId = null
  swipeStartX = null
  swipeStartY = null
  swipeLastX = null
  swipeLastTime = 0
  swipeVelocityX = 0
  swipeDeltaX = 0
  swipeActive = false
}

function applySwipeTransform(): void {
  swipeFrame = null
  const content = contentElement()
  if (!content || !swipeActive) return
  content.style.willChange = 'transform'
  content.style.transform = `translate3d(${swipeDeltaX}px,0,0)`
}

function scheduleSwipeTransform(): void {
  if (swipeFrame != null) return
  swipeFrame = requestAnimationFrame(applySwipeTransform)
}

export function installNavigationTransitions(): void {
  if (installed || typeof document === 'undefined') return
  installed = true

  document.addEventListener('click', event => {
    const target = event.target instanceof HTMLElement ? event.target.closest('button') as HTMLButtonElement | null : null
    if (!target || !isPrimaryNavButton(target) || swipeActive || navigationInProgress) return
    const buttons = primaryButtons()
    const index = buttons.findIndex(button => button === target)
    if (index >= 0) lastKnownIndex = index
    prepareNavColorTransitions()
    preparePagerSurface()
  }, true)

  const initialize = () => {
    prepareNavColorTransitions()
    preparePagerSurface()
    const buttons = primaryButtons()
    if (buttons.length) activeNavIndex(buttons)
  }
  initialize()
  window.setTimeout(initialize, 250)
  window.setTimeout(initialize, 1000)

  // Pointer Events are used instead of separate touchstart/touchmove/touchend
  // paths. They provide one gesture model across Android touchscreens, tablets,
  // pens and desktop input, and pointer capture prevents a swipe from stopping
  // when the finger crosses a child element or leaves the content bounds.
  document.addEventListener('pointerdown', event => {
    if (event.pointerType !== 'touch' || !isPrimarySwipeScreen() || navigationInProgress || event.isPrimary === false || isHorizontalScroller(event.target)) return
    const target = event.target instanceof HTMLElement ? event.target : null
    if (target?.closest('input, textarea, select, button, [contenteditable="true"], a')) return
    const content = contentElement()
    if (!content) return

    cancelSwipeAnimation()
    resetContentTransform()
    preparePagerSurface()

    swipePointerId = event.pointerId
    swipeStartX = event.clientX
    swipeStartY = event.clientY
    swipeLastX = event.clientX
    swipeLastTime = event.timeStamp
    swipeVelocityX = 0
    swipeDeltaX = 0
    swipeActive = false

    try { content.setPointerCapture(event.pointerId) } catch { /* browser may already own capture */ }
  }, { capture: true, passive: true })

  document.addEventListener('pointermove', event => {
    if (event.pointerType !== 'touch' || swipePointerId !== event.pointerId || swipeStartX == null || swipeStartY == null) return

    const dx = event.clientX - swipeStartX
    const dy = event.clientY - swipeStartY
    const absX = Math.abs(dx)
    const absY = Math.abs(dy)

    if (!swipeActive) {
      if (absX < SWIPE_ACTIVATION_DISTANCE && absY < SWIPE_ACTIVATION_DISTANCE) return
      if (absY >= absX * 1.12 || absX <= absY) {
        resetSwipeState()
        return
      }
      swipeActive = true
    }

    event.preventDefault()

    const now = event.timeStamp || performance.now()
    const previousX = swipeLastX ?? event.clientX
    const elapsed = Math.max(1, now - swipeLastTime)
    swipeVelocityX = (event.clientX - previousX) / elapsed
    swipeLastX = event.clientX
    swipeLastTime = now

    const buttons = primaryButtons()
    const active = activeNavIndex(buttons)
    const atStart = active <= 0 && dx > 0
    const atEnd = active >= buttons.length - 1 && dx < 0
    // Follow the finger directly through the page. At either boundary use a
    // rubber-band resistance instead of allowing the surface to leave the app.
    swipeDeltaX = dx * (atStart || atEnd ? 0.35 : 1)
    scheduleSwipeTransform()
  }, { capture: true, passive: false })

  const finishPointer = (event: PointerEvent, cancelled = false) => {
    if (swipePointerId !== event.pointerId) return
    const wasActive = swipeActive
    const delta = swipeDeltaX
    const velocity = swipeVelocityX
    const shouldNavigate = !cancelled
      && isPrimarySwipeScreen()
      && wasActive
      && (Math.abs(delta) >= SWIPE_THRESHOLD || Math.abs(velocity) >= SWIPE_VELOCITY_THRESHOLD)

    if (shouldNavigate) navigateBySwipe(delta < 0 ? 'next' : 'previous')
    else if (wasActive) animateBack()
    else resetContentTransform()

    try {
      const content = contentElement()
      if (content?.hasPointerCapture(event.pointerId)) content.releasePointerCapture(event.pointerId)
    } catch { /* pointer may already have been released */ }
    resetSwipeState()
  }

  document.addEventListener('pointerup', event => finishPointer(event), { capture: true, passive: true })
  document.addEventListener('pointercancel', event => finishPointer(event, true), { capture: true, passive: true })
}
