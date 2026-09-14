let installed = false
let lastKnownIndex: number | null = null
let activePointerId: number | null = null
let swipeStartX: number | null = null
let swipeStartY: number | null = null
let swipeDeltaX = 0
let swipeActive = false
let swipeTarget: EventTarget | null = null
let swipeAnimation: Animation | null = null
let navigationInProgress = false

const PRIMARY_NAV_LABELS = ['home', 'explore', 'chats', 'profile']
const SWIPE_THRESHOLD = 56
const FOLLOW_FACTOR = 1
const MOTION_EASE = 'cubic-bezier(.22,.8,.22,1)'
const COLOR_EASE = 'color 220ms cubic-bezier(.22,.8,.22,1)'
const TRANSITION_DURATION = 240

function navLabel(button: HTMLElement): string {
  return `${button.getAttribute('aria-label') || ''} ${button.getAttribute('title') || ''} ${button.textContent || ''}`.trim().toLowerCase()
}

function isPrimaryNavButton(button: HTMLElement): boolean {
  const label = navLabel(button)
  if (!button.querySelector('svg')) return false
  return PRIMARY_NAV_LABELS.some(item => label === item || label.includes(item))
}

function primaryButtons(): HTMLButtonElement[] {
  const found = Array.from(document.querySelectorAll<HTMLButtonElement>('button')).filter(isPrimaryNavButton)
  return PRIMARY_NAV_LABELS
    .map(label => found.find(button => navLabel(button).includes(label)) || null)
    .filter(Boolean) as HTMLButtonElement[]
}

function activeNavIndex(buttons: HTMLButtonElement[]): number {
  const explicit = buttons.findIndex(button => {
    const style = getComputedStyle(button)
    const label = navLabel(button)
    return button.getAttribute('aria-current') === 'page'
      || button.getAttribute('data-state') === 'active'
      || /active|selected|current/.test(button.className)
      || style.fontWeight === '800'
      || style.fontWeight === '700'
      || button.getAttribute('aria-pressed') === 'true'
      || button.querySelector('[aria-current="page"]') !== null
      || (label.includes('home') && lastKnownIndex == null)
  })
  if (explicit >= 0) {
    lastKnownIndex = explicit
    return explicit
  }
  return lastKnownIndex ?? 0
}

function contentElement(): HTMLElement | null {
  const root = document.getElementById('root')
  const appShell = root?.firstElementChild
  const content = appShell?.firstElementChild
  return content instanceof HTMLElement ? content : null
}

function cancelSwipeAnimation(): void {
  swipeAnimation?.cancel()
  swipeAnimation = null
}

function resetContentTransform(): void {
  const content = contentElement()
  if (!content) return
  content.style.transform = ''
  content.style.willChange = ''
}

function prepareNavColorTransitions(): void {
  primaryButtons().forEach(button => {
    if (!button.style.transition.includes(COLOR_EASE)) {
      button.style.transition = button.style.transition
        ? `${button.style.transition}, ${COLOR_EASE}`
        : COLOR_EASE
    }
  })
}

function preparePagerSurface(): void {
  const content = contentElement()
  if (!content) return
  // Vertical scrolling remains native. Horizontal movement belongs to the
  // pager, so Android Chrome does not steal the horizontal gesture.
  content.style.touchAction = 'pan-y pinch-zoom'
  content.style.overscrollBehaviorX = 'none'
}

function copyScrollPositions(source: Element, target: Element): void {
  if (source instanceof HTMLElement && target instanceof HTMLElement) {
    target.scrollTop = source.scrollTop
    target.scrollLeft = source.scrollLeft
  }
  const sourceChildren = Array.from(source.children)
  const targetChildren = Array.from(target.children)
  for (let i = 0; i < sourceChildren.length; i += 1) {
    const targetChild = targetChildren[i]
    if (targetChild) copyScrollPositions(sourceChildren[i], targetChild)
  }
}

function stripCloneIds(root: Element): void {
  if (root instanceof HTMLElement) root.removeAttribute('id')
  root.querySelectorAll('[id]').forEach(node => node.removeAttribute('id'))
}

function createOutgoingLayer(content: HTMLElement): HTMLElement | null {
  const rect = content.getBoundingClientRect()
  if (rect.width <= 0 || rect.height <= 0) return null

  const host = document.createElement('div')
  host.setAttribute('aria-hidden', 'true')
  host.dataset.prepzaNavLayer = 'outgoing'
  Object.assign(host.style, {
    position: 'fixed',
    left: `${rect.left}px`,
    top: `${rect.top}px`,
    width: `${rect.width}px`,
    height: `${rect.height}px`,
    overflow: 'hidden',
    zIndex: '2147483645',
    pointerEvents: 'none',
    background: getComputedStyle(content).backgroundColor || 'transparent',
    transform: `translate3d(${swipeDeltaX}px,0,0)`,
    willChange: 'transform',
  })

  const clone = content.cloneNode(true) as HTMLElement
  stripCloneIds(clone)
  Object.assign(clone.style, {
    position: 'absolute',
    left: '0',
    top: '0',
    width: `${content.offsetWidth}px`,
    minHeight: `${content.offsetHeight}px`,
    transform: 'none',
    overflow: getComputedStyle(content).overflow,
    pointerEvents: 'none',
  })
  host.appendChild(clone)
  document.body.appendChild(host)
  copyScrollPositions(content, clone)
  return host
}

function cleanupOutgoingLayer(layer: HTMLElement | null): void {
  layer?.remove()
}

function animateBack(): void {
  const content = contentElement()
  if (!content) return
  cancelSwipeAnimation()
  swipeAnimation = content.animate(
    [
      { transform: `translate3d(${swipeDeltaX}px,0,0)` },
      { transform: 'translate3d(0,0,0)' },
    ],
    { duration: TRANSITION_DURATION, easing: MOTION_EASE, fill: 'forwards' },
  )
  swipeAnimation.onfinish = () => {
    swipeAnimation = null
    resetContentTransform()
  }
}

function finishNavigation(direction: 'left' | 'right', navigate: () => void): void {
  if (navigationInProgress) return
  const content = contentElement()
  if (!content) {
    navigate()
    return
  }

  navigationInProgress = true
  cancelSwipeAnimation()

  // Keep the exact current screen visible while React replaces the page.
  // The old screen is a visual layer; the newly rendered screen enters beside
  // it in the same animation frame. This is the key difference from the old
  // exit-then-render approach that produced a white frame.
  const outgoingLayer = createOutgoingLayer(content)
  const sign = direction === 'left' ? -1 : 1
  const width = Math.max(window.innerWidth, content.clientWidth || 0)

  content.style.visibility = 'hidden'
  content.style.transform = `translate3d(${-sign * width}px,0,0)`
  content.style.willChange = 'transform'

  navigate()

  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      const nextContent = contentElement()
      if (!nextContent) {
        cleanupOutgoingLayer(outgoingLayer)
        navigationInProgress = false
        return
      }

      nextContent.style.visibility = 'visible'
      nextContent.style.willChange = 'transform'
      nextContent.style.transform = `translate3d(${-sign * width}px,0,0)`

      const outgoingStart = swipeDeltaX
      const outgoingEnd = sign * width
      const incomingStart = -sign * width

      const outgoingAnimation = outgoingLayer?.animate(
        [
          { transform: `translate3d(${outgoingStart}px,0,0)` },
          { transform: `translate3d(${outgoingEnd}px,0,0)` },
        ],
        { duration: TRANSITION_DURATION, easing: MOTION_EASE, fill: 'forwards' },
      )

      const incomingAnimation = nextContent.animate(
        [
          { transform: `translate3d(${incomingStart}px,0,0)` },
          { transform: 'translate3d(0,0,0)' },
        ],
        { duration: TRANSITION_DURATION, easing: MOTION_EASE, fill: 'forwards' },
      )

      Promise.allSettled([outgoingAnimation?.finished, incomingAnimation.finished]).then(() => {
        cleanupOutgoingLayer(outgoingLayer)
        resetContentTransform()
        nextContent.style.visibility = ''
        nextContent.style.willChange = ''
        navigationInProgress = false
      })
    })
  })
}

function navigateBySwipe(direction: 'next' | 'previous'): void {
  const buttons = primaryButtons()
  if (!buttons.length) return
  const active = activeNavIndex(buttons)
  const nextIndex = direction === 'next' ? active + 1 : active - 1
  if (nextIndex < 0 || nextIndex >= buttons.length) {
    animateBack()
    return
  }

  lastKnownIndex = nextIndex
  finishNavigation(direction === 'next' ? 'left' : 'right', () => buttons[nextIndex].click())
}

function isHorizontalScroller(target: EventTarget | null): boolean {
  let node = target instanceof HTMLElement ? target : null
  while (node && node !== document.body) {
    const style = getComputedStyle(node)
    if ((style.overflowX === 'auto' || style.overflowX === 'scroll') && node.scrollWidth > node.clientWidth + 4) return true
    node = node.parentElement
  }
  return false
}

function resetPointerState(): void {
  swipeStartX = null
  swipeStartY = null
  swipeDeltaX = 0
  swipeActive = false
  swipeTarget = null
  activePointerId = null
}

export function installNavigationTransitions(): void {
  if (installed || typeof document === 'undefined') return
  installed = true

  document.addEventListener('click', event => {
    const target = event.target instanceof HTMLElement
      ? event.target.closest('button') as HTMLElement | null
      : null
    if (!target || !isPrimaryNavButton(target) || swipeActive || navigationInProgress) return
    const buttons = primaryButtons()
    const index = buttons.findIndex(button => button === target)
    if (index >= 0) lastKnownIndex = index
    prepareNavColorTransitions()
    preparePagerSurface()
  }, true)

  const initializeNav = () => {
    prepareNavColorTransitions()
    preparePagerSurface()
    const buttons = primaryButtons()
    if (buttons.length) lastKnownIndex = activeNavIndex(buttons)
  }

  initializeNav()
  window.setTimeout(initializeNav, 250)
  window.setTimeout(initializeNav, 1000)

  document.addEventListener('pointerdown', event => {
    if (navigationInProgress || event.pointerType === 'mouse' && event.button !== 0) return
    if (event.isPrimary === false || isHorizontalScroller(event.target)) return

    const target = event.target instanceof HTMLElement ? event.target : null
    if (target?.closest('input, textarea, [contenteditable="true"], button')) return

    const content = contentElement()
    if (!content) return

    cancelSwipeAnimation()
    resetContentTransform()
    preparePagerSurface()
    swipeStartX = event.clientX
    swipeStartY = event.clientY
    swipeTarget = event.target
    swipeDeltaX = 0
    swipeActive = false
    activePointerId = event.pointerId
  }, { capture: true })

  document.addEventListener('pointermove', event => {
    if (activePointerId == null || event.pointerId !== activePointerId || swipeStartX == null || swipeStartY == null) return

    const dx = event.clientX - swipeStartX
    const dy = event.clientY - swipeStartY

    if (!swipeActive) {
      if (Math.abs(dx) < 8 && Math.abs(dy) < 8) return
      if (Math.abs(dy) > Math.abs(dx) * 1.12) {
        resetPointerState()
        return
      }
      if (Math.abs(dx) <= Math.abs(dy)) return

      const content = contentElement()
      if (!content) return
      try { content.setPointerCapture(event.pointerId) } catch { /* already captured or unavailable */ }
      swipeActive = true
    }

    const buttons = primaryButtons()
    const active = activeNavIndex(buttons)
    const atStart = active <= 0 && dx > 0
    const atEnd = active >= buttons.length - 1 && dx < 0
    const resistance = atStart || atEnd ? 0.35 : FOLLOW_FACTOR
    swipeDeltaX = dx * resistance

    const content = contentElement()
    if (content) {
      content.style.willChange = 'transform'
      content.style.transform = `translate3d(${swipeDeltaX}px,0,0)`
    }
  }, { capture: true })

  const finishPointer = (event: PointerEvent) => {
    if (activePointerId == null || event.pointerId !== activePointerId) return

    const rawDx = swipeDeltaX / FOLLOW_FACTOR
    const shouldNavigate = swipeActive && Math.abs(rawDx) >= SWIPE_THRESHOLD

    if (shouldNavigate) {
      navigateBySwipe(rawDx < 0 ? 'next' : 'previous')
    } else if (swipeActive) {
      animateBack()
    }

    resetPointerState()
  }

  document.addEventListener('pointerup', finishPointer, { capture: true })
  document.addEventListener('pointercancel', finishPointer, { capture: true })
}
