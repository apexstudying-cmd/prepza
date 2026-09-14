let installed = false
let lastKnownIndex: number | null = null
let swipeStartX: number | null = null
let swipeStartY: number | null = null
let swipeDeltaX = 0
let swipeActive = false
let swipeAnimation: Animation | null = null
let navigationInProgress = false

const PRIMARY_NAV_LABELS = ['home', 'explore', 'chats', 'profile']
const SWIPE_THRESHOLD = 56
const TRANSITION_DURATION = 240
const MOTION_EASE = 'cubic-bezier(.22,.8,.22,1)'
const COLOR_EASE = 'color 220ms cubic-bezier(.22,.8,.22,1)'

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
  if (lastKnownIndex != null && lastKnownIndex >= 0 && lastKnownIndex < buttons.length) return lastKnownIndex

  const active = buttons.findIndex(button => {
    const className = typeof button.className === 'string' ? button.className : ''
    return button.getAttribute('aria-current') === 'page'
      || button.getAttribute('data-state') === 'active'
      || button.getAttribute('aria-pressed') === 'true'
      || button.querySelector('[aria-current="page"]') !== null
      || /(^|[\s_-])(active|selected|current)([\s_-]|$)/i.test(className)
  })

  lastKnownIndex = active >= 0 ? active : 0
  return lastKnownIndex
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
}

function preparePagerSurface(): void {
  const content = contentElement()
  if (!content) return
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
  const sourceChildren = Array.from(source.children)
  const targetChildren = Array.from(target.children)
  sourceChildren.forEach((child, index) => {
    const targetChild = targetChildren[index]
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
    zIndex: '40',
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

  const outgoingLayer = createOutgoingLayer(content)
  const sign = direction === 'left' ? -1 : 1
  const width = Math.max(window.innerWidth, content.clientWidth || 0)

  // The outgoing layer keeps the current screen painted while React changes
  // the actual screen underneath it. The two screens then animate together.
  content.style.visibility = 'hidden'
  content.style.transform = `translate3d(${-sign * width}px,0,0)`
  content.style.willChange = 'transform'

  navigate()

  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      const nextContent = contentElement()
      if (!nextContent) {
        outgoingLayer?.remove()
        navigationInProgress = false
        return
      }

      nextContent.style.visibility = 'visible'
      nextContent.style.willChange = 'transform'
      nextContent.style.transform = `translate3d(${-sign * width}px,0,0)`

      const outgoingAnimation = outgoingLayer?.animate(
        [
          { transform: `translate3d(${swipeDeltaX}px,0,0)` },
          { transform: `translate3d(${sign * width}px,0,0)` },
        ],
        { duration: TRANSITION_DURATION, easing: MOTION_EASE, fill: 'forwards' },
      )
      const incomingAnimation = nextContent.animate(
        [
          { transform: `translate3d(${-sign * width}px,0,0)` },
          { transform: 'translate3d(0,0,0)' },
        ],
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
  })
}

function navigateBySwipe(direction: 'next' | 'previous'): void {
  const buttons = primaryButtons()
  if (buttons.length < 2) return
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
  const pager = contentElement()
  let node = target instanceof HTMLElement ? target : null
  while (node && node !== document.body) {
    // The pager itself is the gesture surface. Only nested horizontal
    // scrollers should consume horizontal swipes.
    if (node === pager) break
    const style = getComputedStyle(node)
    if ((style.overflowX === 'auto' || style.overflowX === 'scroll') && node.scrollWidth > node.clientWidth + 4) return true
    node = node.parentElement
  }
  return false
}

function resetSwipeState(): void {
  swipeStartX = null
  swipeStartY = null
  swipeDeltaX = 0
  swipeActive = false
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

  // Touch Events are used here deliberately. On Android Chrome they let the
  // app distinguish a horizontal pager gesture from vertical scrolling before
  // calling preventDefault; Pointer Events in the previous implementation
  // were getting cancelled before the pager could move.
  document.addEventListener('touchstart', event => {
    if (navigationInProgress || event.touches.length !== 1 || isHorizontalScroller(event.target)) return
    const target = event.target instanceof HTMLElement ? event.target : null
    if (target?.closest('input, textarea, select, button, [contenteditable="true"]')) return

    const content = contentElement()
    if (!content) return
    cancelSwipeAnimation()
    resetContentTransform()
    preparePagerSurface()
    swipeStartX = event.touches[0].clientX
    swipeStartY = event.touches[0].clientY
    swipeDeltaX = 0
    swipeActive = false
  }, { capture: true, passive: true })

  document.addEventListener('touchmove', event => {
    if (swipeStartX == null || swipeStartY == null || event.touches.length !== 1) return

    const dx = event.touches[0].clientX - swipeStartX
    const dy = event.touches[0].clientY - swipeStartY

    if (!swipeActive) {
      if (Math.abs(dx) < 8 && Math.abs(dy) < 8) return
      if (Math.abs(dy) >= Math.abs(dx) * 1.12 || Math.abs(dx) <= Math.abs(dy)) {
        resetSwipeState()
        return
      }
      swipeActive = true
    }

    event.preventDefault()
    const buttons = primaryButtons()
    const active = activeNavIndex(buttons)
    const atStart = active <= 0 && dx > 0
    const atEnd = active >= buttons.length - 1 && dx < 0
    const resistance = atStart || atEnd ? 0.35 : 1
    swipeDeltaX = dx * resistance

    const content = contentElement()
    if (content) {
      content.style.willChange = 'transform'
      content.style.transform = `translate3d(${swipeDeltaX}px,0,0)`
    }
  }, { capture: true, passive: false })

  const finishTouch = (event: TouchEvent) => {
    if (swipeStartX == null || swipeStartY == null) return
    const shouldNavigate = swipeActive && Math.abs(swipeDeltaX) >= SWIPE_THRESHOLD

    if (shouldNavigate) {
      navigateBySwipe(swipeDeltaX < 0 ? 'next' : 'previous')
    } else if (swipeActive) {
      animateBack()
    }

    resetSwipeState()
  }

  document.addEventListener('touchend', finishTouch, { capture: true, passive: true })
  document.addEventListener('touchcancel', finishTouch, { capture: true, passive: true })
}
