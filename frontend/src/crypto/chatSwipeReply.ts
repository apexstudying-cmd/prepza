type SwipeState = {
  startX: number
  startY: number
  currentX: number
  lockedHorizontal: boolean
}

const MESSAGE_PREFIX = 'prepza-msg-'
const SWIPE_THRESHOLD = 64
const MAX_TRANSLATE = 72

function isMessageRow(element: Element | null): element is HTMLElement {
  return element instanceof HTMLElement && element.id.startsWith(MESSAGE_PREFIX)
}

function replyButtonFor(row: HTMLElement): HTMLButtonElement | null {
  const buttons = row.querySelectorAll('button')
  for (const button of buttons) {
    if (button.getAttribute('title') === 'Reply') return button as HTMLButtonElement
  }
  return null
}

function installOnRow(row: HTMLElement): void {
  if (row.dataset.prepzaSwipeReply === '1') return
  row.dataset.prepzaSwipeReply = '1'
  row.style.touchAction = 'pan-y'
  row.style.willChange = 'transform'
  row.style.transition = 'transform 120ms ease-out'

  let state: SwipeState | null = null

  row.addEventListener('touchstart', event => {
    if (event.touches.length !== 1) return
    const touch = event.touches[0]
    state = {
      startX: touch.clientX,
      startY: touch.clientY,
      currentX: touch.clientX,
      lockedHorizontal: false,
    }
    row.style.transition = 'none'
  }, { passive: true })

  row.addEventListener('touchmove', event => {
    if (!state || event.touches.length !== 1) return
    const touch = event.touches[0]
    state.currentX = touch.clientX
    const dx = touch.clientX - state.startX
    const dy = touch.clientY - state.startY

    if (!state.lockedHorizontal) {
      if (Math.abs(dx) < 8 && Math.abs(dy) < 8) return
      if (Math.abs(dy) > Math.abs(dx)) {
        state = null
        row.style.transition = 'transform 120ms ease-out'
        row.style.transform = ''
        return
      }
      state.lockedHorizontal = true
    }

    event.preventDefault()
    const translate = Math.max(-MAX_TRANSLATE, Math.min(MAX_TRANSLATE, dx))
    row.style.transform = `translateX(${translate}px)`
  }, { passive: false })

  row.addEventListener('touchend', () => {
    if (!state) return
    const dx = state.currentX - state.startX
    const shouldReply = state.lockedHorizontal && Math.abs(dx) >= SWIPE_THRESHOLD
    state = null
    row.style.transition = 'transform 120ms ease-out'
    row.style.transform = ''

    if (shouldReply) {
      const replyButton = replyButtonFor(row)
      if (replyButton) {
        try { navigator.vibrate?.(8) } catch { /* vibration is optional */ }
        replyButton.click()
      }
    }
  }, { passive: true })

  row.addEventListener('touchcancel', () => {
    state = null
    row.style.transition = 'transform 120ms ease-out'
    row.style.transform = ''
  }, { passive: true })
}

export function installChatSwipeReply(): void {
  const scan = () => {
    document.querySelectorAll<HTMLElement>(`[id^="${MESSAGE_PREFIX}"]`).forEach(installOnRow)
  }

  scan()
  const observer = new MutationObserver(scan)
  observer.observe(document.body, { childList: true, subtree: true })
}
