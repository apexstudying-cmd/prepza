let installed = false
let swipeStartX: number | null = null
let swipeStartY: number | null = null
let swipeTarget: EventTarget | null = null
let swipeDeltaX = 0
let swipeActive = false
let lastKnownIndex: number | null = null
let swipeAnimation: Animation | null = null

const PRIMARY_NAV_LABELS = ['home', 'explore', 'chats', 'profile']

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

function finishNavigation(direction: 'left' | 'right', navigate: () => void): void {
  const root = rootElement()
  if (!root) {
    navigate()
    return
  }

  cancelSwipeAnimation()
  root.style.willChange = 'transform, opacity'
  const sign = direction === 'left' ? -1 : 1
  const exitDistance = Math.min(window.innerWidth * 0.20, 120)

  swipeAnimation = root.animate(
    [
      { transform: `translate3d(${swipeDeltaX}px,0,0)`, opacity: 1 },
      { transform: `translate3d(${sign * exitDistance}px,0,0)`, opacity: .78 },
    ],
    { duration: 150, easing: 'cubic-bezier(.32,.72,0,1)', fill: 'forwards' },
  )

  swipeAnimation.onfinish = () => {
    swipeAnimation = null
    navigate()

    requestAnimationFrame(() => {
      root.style.transform = `translate3d(${-sign * Math.min(window.innerWidth * .10, 64)}px,0,0)`
      root.style.opacity = '.78'
      swipeAnimation = root.animate(
        [
          { transform: root.style.transform, opacity: .78 },
          { transform: 'translate3d(0,0,0)', opacity: 1 },
        ],
        { duration: 280, easing: 'cubic-bezier(.22,1,.36,1)', fill: 'forwards' },
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
    const root = rootElement()
    if (root && swipeActive) {
      cancelSwipeAnimation()
      swipeAnimation = root.animate(
        [
          { transform: `translate3d(${swipeDeltaX}px,0,0)` },
          { transform: 'translate3d(0,0,0)' },
        ],
        { duration: 220, easing: 'cubic-bezier(.22,1,.36,1)', fill: 'forwards' },
      )
      swipeAnimation.onfinish = () => {
        swipeAnimation = null
        resetRootTransform()
      }
    }
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

  // Direct taps retain the app's normal instant navigation. The enhanced motion
  // is reserved for touch swipes so tapping never gets a double transition.
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

    // A vertical gesture belongs to the page scroll. Only take ownership after
    // the horizontal direction is clearly established.
    if (!swipeActive && Math.abs(dy) > Math.abs(dx) * 1.15) return
    if (Math.abs(dx) < 8 || Math.abs(dx) < Math.abs(dy) * 1.15) return

    swipeActive = true
    const resistance = Math.abs(dx) > window.innerWidth * .55 ? .30 : .58
    swipeDeltaX = dx * resistance

    const root = rootElement()
    if (root) {
      root.style.willChange = 'transform, opacity'
      root.style.transform = `translate3d(${swipeDeltaX}px,0,0)`
      root.style.opacity = String(1 - Math.min(Math.abs(swipeDeltaX) / 900, .12))
    }
  }, { passive: true, capture: true })

  document.addEventListener('touchend', () => {
    if (swipeStartX == null || swipeStartY == null) return

    const dx = swipeDeltaX / .58
    const shouldNavigate = swipeActive && Math.abs(dx) >= 72

    if (shouldNavigate) {
      navigateBySwipe(dx < 0 ? 'next' : 'previous')
    } else if (swipeActive) {
      const root = rootElement()
      if (root) {
        cancelSwipeAnimation()
        swipeAnimation = root.animate(
          [
            { transform: `translate3d(${swipeDeltaX}px,0,0)`, opacity: parseFloat(root.style.opacity || '1') },
            { transform: 'translate3d(0,0,0)', opacity: 1 },
          ],
          { duration: 220, easing: 'cubic-bezier(.22,1,.36,1)', fill: 'forwards' },
        )
        swipeAnimation.onfinish = () => {
          swipeAnimation = null
          resetRootTransform()
        }
      }
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
