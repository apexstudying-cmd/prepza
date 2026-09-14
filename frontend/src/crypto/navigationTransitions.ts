let installed = false
let swipeStartX: number | null = null
let swipeStartY: number | null = null
let swipeTarget: EventTarget | null = null
let swipeTriggered = false
let lastKnownIndex: number | null = null

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

function animate(direction: 'left' | 'right') {
  const root = document.getElementById('root')
  if (!root) return
  root.animate(
    direction === 'left'
      ? [{ transform: 'translateX(0)', opacity: 1 }, { transform: 'translateX(-28px)', opacity: .94 }, { transform: 'translateX(0)', opacity: 1 }]
      : [{ transform: 'translateX(0)', opacity: 1 }, { transform: 'translateX(28px)', opacity: .94 }, { transform: 'translateX(0)', opacity: 1 }],
    { duration: 260, easing: 'cubic-bezier(.22,.61,.36,1)' },
  )
}

function navigateBySwipe(direction: 'next' | 'previous') {
  const buttons = primaryButtons()
  if (!buttons.length) return
  const active = activeNavIndex(buttons)
  const nextIndex = direction === 'next' ? active + 1 : active - 1
  if (nextIndex < 0 || nextIndex >= buttons.length) return
  lastKnownIndex = nextIndex
  animate(direction === 'next' ? 'left' : 'right')
  buttons[nextIndex].click()
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
    if (!target || !isPrimaryNavButton(target)) return
    const buttons = primaryButtons()
    const index = buttons.findIndex(button => button === target)
    if (index < 0) return
    const active = activeNavIndex(buttons)
    if (active === index) return
    lastKnownIndex = index
    animate(index > active ? 'left' : 'right')
  }, true)

  // Native-feeling horizontal swipe between Home → Explore → Chats → Profile.
  // Vertical movement remains normal scrolling, and horizontal carousels keep
  // ownership of their own gestures.
  document.addEventListener('touchstart', event => {
    if (event.touches.length !== 1 || isHorizontalScroller(event.target)) return
    const target = event.target instanceof HTMLElement ? event.target : null
    if (target?.closest('input, textarea, [contenteditable="true"]')) return
    swipeStartX = event.touches[0]?.clientX ?? null
    swipeStartY = event.touches[0]?.clientY ?? null
    swipeTarget = event.target
    swipeTriggered = false
  }, { passive: true, capture: true })

  document.addEventListener('touchmove', event => {
    if (swipeStartX == null || swipeStartY == null || swipeTriggered || !swipeTarget || event.touches.length !== 1) return
    const dx = (event.touches[0]?.clientX ?? swipeStartX) - swipeStartX
    const dy = (event.touches[0]?.clientY ?? swipeStartY) - swipeStartY
    if (Math.abs(dx) < 72 || Math.abs(dx) < Math.abs(dy) * 1.35) return
    swipeTriggered = true
    navigateBySwipe(dx < 0 ? 'next' : 'previous')
  }, { passive: true, capture: true })

  const reset = () => { swipeStartX = null; swipeStartY = null; swipeTarget = null; swipeTriggered = false }
  document.addEventListener('touchend', reset, { passive: true, capture: true })
  document.addEventListener('touchcancel', reset, { passive: true, capture: true })
}
