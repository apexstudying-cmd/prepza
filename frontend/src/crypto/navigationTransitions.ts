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
const FOLLOW_FACTOR = 1
const MOTION_EASE = 'cubic-bezier(.22,.8,.22,1)'
const COLOR_EASE = 'color 220ms cubic-bezier(.22,.8,.22,1)'

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
    if (!button.style.transition.includes('color 220ms cubic-bezier(.22,.8,.22,1)')) {
      button.style.transition = button.style.transition
        ? `${button.style.transition}, ${COLOR_EASE}`
        : COLOR_EASE
    }
  })
}

function installViewTransitionStyles(): void {
  if (document.getElementById('prepza-primary-nav-transition-styles')) return

  const style = document.createElement('style')
  style.id = 'prepza-primary-nav-transition-styles'
  style.textContent = `
    @keyframes prepza-nav-old-left {
      from { transform: translateX(0); }
      to { transform: translateX(-100%); }
    }
    @keyframes prepza-nav-old-right {
      from { transform: translateX(0); }
      to { transform: translateX(100%); }
    }
    @keyframes prepza-nav-new-left {
      from { transform: translateX(100%); }
      to { transform: translateX(0); }
    }
    @keyframes prepza-nav-new-right {
      from { transform: translateX(-100%); }
      to { transform: translateX(0); }
    }

    ::view-transition-old(prepza-primary-content),
    ::view-transition-new(prepza-primary-content) {
      animation-duration: 240ms;
      animation-timing-function: cubic-bezier(.22,.8,.22,1);
      animation-fill-mode: both;
      mix-blend-mode: normal;
    }

    html.prepza-nav-left ::view-transition-old(prepza-primary-content) {
      animation-name: prepza-nav-old-left;
    }
    html.prepza-nav-left ::view-transition-new(prepza-primary-content) {
      animation-name: prepza-nav-new-left;
    }
    html.prepza-nav-right ::view-transition-old(prepza-primary-content) {
      animation-name: prepza-nav-old-right;
    }
    html.prepza-nav-right ::view-transition-new(prepza-primary-content) {
      animation-name: prepza-nav-new-right;
    }
  `
  document.head.appendChild(style)
}

function prepareViewTransitionTarget(): void {
  const content = contentElement()
  if (!content) return
  content.style.viewTransitionName = 'prepza-primary-content'
  content.style.contain = 'paint'
}

function runViewTransition(direction: 'left' | 'right', navigate: () => void): void {
  const content = contentElement()
  if (!content) {
    navigate()
    return
  }

  prepareViewTransitionTarget()
  installViewTransitionStyles()

  const html = document.documentElement
  html.classList.remove('prepza-nav-left', 'prepza-nav-right')
  html.classList.add(direction === 'left' ? 'prepza-nav-left' : 'prepza-nav-right')

  const startViewTransition = (document as Document & {
    startViewTransition?: (update: () => void) => { finished?: Promise<void> }
  }).startViewTransition

  if (!startViewTransition) {
    cancelSwipeAnimation()
    content.animate(
      [
        { transform: `translate3d(${swipeDeltaX}px,0,0)` },
        { transform: `translate3d(${direction === 'left' ? -100 : 100}%,0,0)` },
      ],
      { duration: 240, easing: MOTION_EASE, fill: 'forwards' },
    ).onfinish = () => {
      navigate()
      resetContentTransform()
    }
    return
  }

  // The browser captures the current page and the next page before animating
  // them as two adjacent layers. This prevents the blank-frame problem caused
  // by replacing the React screen only after the old page has left the viewport.
  startViewTransition(() => {
    resetContentTransform()
    navigate()
  }).finished?.finally(() => {
    html.classList.remove('prepza-nav-left', 'prepza-nav-right')
    resetContentTransform()
  })
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
    { duration: 240, easing: MOTION_EASE, fill: 'forwards' },
  )
  swipeAnimation.onfinish = () => {
    swipeAnimation = null
    resetContentTransform()
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
  runViewTransition(direction === 'next' ? 'left' : 'right', () => buttons[nextIndex].click())
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
    prepareNavColorTransitions()
    prepareViewTransitionTarget()
  }, true)

  const initializeNav = () => {
    prepareNavColorTransitions()
    prepareViewTransitionTarget()
    const buttons = primaryButtons()
    if (buttons.length) lastKnownIndex = activeNavIndex(buttons)
  }

  initializeNav()
  window.setTimeout(initializeNav, 250)
  window.setTimeout(initializeNav, 1000)

  document.addEventListener('touchstart', event => {
    if (event.touches.length !== 1 || isHorizontalScroller(event.target)) return
    const target = event.target instanceof HTMLElement ? event.target : null
    if (target?.closest('input, textarea, [contenteditable="true"]')) return
    cancelSwipeAnimation()
    resetContentTransform()
    prepareNavColorTransitions()
    prepareViewTransitionTarget()
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

    const content = contentElement()
    if (content) {
      content.style.willChange = 'transform'
      content.style.transform = `translate3d(${swipeDeltaX}px,0,0)`
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
    resetContentTransform()
  }, { passive: true, capture: true })
}
