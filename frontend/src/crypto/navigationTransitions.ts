let installed = false
let swipeStartX: number | null = null
let swipeStartY: number | null = null
let swipeTarget: EventTarget | null = null
let swipeDeltaX = 0
let swipeActive = false
let lastKnownIndex: number | null = null
let swipeAnimation: Animation | null = null

const PRIMARY_NAV_LABELS = ['home', 'explore', 'chats', 'profile']
const SWIPE_THRESHOLD = 72
const FOLLOW_FACTOR = 0.82
const MOTION_EASE = 'cubic-bezier(.16,1,.3,1)'

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
  return PRIMARY_NAV_LABELS.map(label => found.find(button => navLabel(button).includes(label)) || null).filter(Boolean) as HTMLButtonElement[]
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

function rootElement(): HTMLElement | null {
  return document.getElementById('root')
}

function cancelSwipeAnimation(): void {
  swipeAnimation?.cancel()
  swipeAnimation = null
}

function resetRootTransform(): void {
  const root = rootElement()
  if (!root) return
  root.style.transform = ''
  root.style.opacity = ''
  root.style.willChange = ''
}

function animateBack(): void {
  const root = rootElement()
  if (!root) return
  cancelSwipeAnimation()
  swipeAnimation = root.animate(
    [
      { transform: `translate3d(${swipeDeltaX}px,0,0)` },
      { transform: 'translate3d(0,0,0)' },
    ],
    { duration: 360, easing: MOTION_EASE, fill: 'forwards' },
  )
  swipeAnimation.onfinish = () => {
    swipeAnimation = null
    resetRootTransform()
  }
}

function finishNavigation(direction: 'left' | 'right', navigate: () => void): void {
  const root = rootElement()
  if (!root) {
    navigate()
    return
  }

  cancelSwipeAnimation()
  root.style.willChange = 'transform'
  const sign = direction === 'left' ? -1 : 1
  const exitDistance = Math.min(window.innerWidth * 0.16, 96)

  swipeAnimation = root.animate(
    [
      { transform: `translate3d(${swipeDeltaX}px,0,0)` },
      { transform: `translate3d(${sign * exitDistance}px,0,0)` },
    ],
    { duration: 190, easing: MOTION_EASE, fill: 'forwards' },
  )

  swipeAnimation.onfinish = () => {
    swipeAnimation = null
    navigate()

    requestAnimationFrame(() => {
      root.style.transform = `translate3d(${-sign * Math.min(window.innerWidth * 0.09, 56)}px,0,0)`
      root.style.willChange = 'transform'
      swipeAnimation = root.animate(
        [
          { transform: root.style.transform },
          { transform: 'translate3d(0,0,0)' },
        ],
        { duration: 360, easing: MOTION_EASE, fill: 'forwards' },
      )
      swipeAnimation.onfinish = () => {
        swipeAnimation = null
        resetRootTransform()
      }
    })
  }
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

export function installNavigationTransitions(): void {
  if (installed || typeof document === 'undefined') return
  installed = true

  document.addEventListener('click', event => {
    const target = event.target instanceof HTMLElement ? event.target.closest('button') as HTMLElement | null : null
    if (!target || !isPrimaryNavButton(target) || swipeActive) return
    const buttons = primaryButtons()
    const index = buttons.findIndex(button => button === target)
    if (index >= 0) lastKnownIndex = index
  }, true)

  document.addEventListener('touchstart', event => {
    if (event.touches.length !== 1 || isHorizontalScroller(event.target)) return
    const target = event.target instanceof HTMLElement ? event.target : null
    if (target?.closest('input, textarea, [contenteditable="true"]')) return
    cancelSwipeAnimation()
    resetRootTransform()
    swipeStartX = event.touches[0]?.clientX ?? null
    swipeStartY = event.touches[0]?.clientY ?? null
    swipeTarget = event.target
    swipeDeltaX = 0
    swipeActive = false
  }, { passive: true, capture: true })

  document.addEventListener('touchmove', event => {
    if (swipeStartX == null || swipeStartY == null || !swipeTarget || event.touches.length !== 1) return
    const dx = (event.touches[0]?.clientX ?? swipeStartX) - swipeStartX
    const dy = (event.touches[0]?.clientY ?? swipeStartY) - swipeStartY

    if (!swipeActive && Math.abs(dy) > Math.abs(dx) * 1.15) return
    if (Math.abs(dx) < 8 || Math.abs(dx) < Math.abs(dy) * 1.15) return

    swipeActive = true
    swipeDeltaX = dx * FOLLOW_FACTOR

    const root = rootElement()
    if (root) {
      root.style.willChange = 'transform'
      root.style.transform = `translate3d(${swipeDeltaX}px,0,0)`
      root.style.opacity = '1'
    }
  }, { passive: true, capture: true })

  document.addEventListener('touchend', () => {
    if (swipeStartX == null || swipeStartY == null) return

    const rawDx = swipeDeltaX / FOLLOW_FACTOR
    const shouldNavigate = swipeActive && Math.abs(rawDx) >= SWIPE_THRESHOLD

    if (shouldNavigate) {
      navigateBySwipe(rawDx < 0 ? 'next' : 'previous')
    } else if (swipeActive) {
      animateBack()
    }

    swipeStartX = null
    swipeStartY = null
    swipeTarget = null
    swipeDeltaX = 0
    swipeActive = false
  }, { passive: true, capture: true })

  document.addEventListener('touchcancel', () => {
    swipeStartX = null
    swipeStartY = null
    swipeTarget = null
    swipeDeltaX = 0
    swipeActive = false
    resetRootTransform()
  }, { passive: true, capture: true })
}
