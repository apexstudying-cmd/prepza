type SwipeState = {
  startX: number
  startY: number
  currentX: number
  lockedHorizontal: boolean
}

const MESSAGE_PREFIX = 'prepza-msg-'
const SWIPE_THRESHOLD = 48
const MAX_TRANSLATE = 76

function isMessageRow(element: EventTarget | null): element is HTMLElement {
  return element instanceof HTMLElement && Boolean(element.closest(`[id^="${MESSAGE_PREFIX}"]`))
}

function messageRow(element: EventTarget | null): HTMLElement | null {
  if (!(element instanceof HTMLElement)) return null
  const row = element.closest(`[id^="${MESSAGE_PREFIX}"]`)
  return row instanceof HTMLElement ? row : null
}

function replyButtonFor(row: HTMLElement): HTMLButtonElement | null {
  const button = row.querySelector<HTMLButtonElement>('button[title="Reply"]')
  return button || null
}

function installOnRow(row: HTMLElement): void {
  if (row.dataset.prepzaSwipeReply === '2') return
  row.dataset.prepzaSwipeReply = '2'
  row.style.touchAction = 'pan-y'
  row.style.willChange = 'transform'

  let state: SwipeState | null = null

  const reset = () => {
    state = null
    row.style.transition = 'transform 140ms ease-out'
    row.style.transform = ''
  }

  row.addEventListener('pointerdown', event => {
    if (event.pointerType === 'mouse' && event.button !== 0) return
    state = {
      startX: event.clientX,
      startY: event.clientY,
      currentX: event.clientX,
      lockedHorizontal: false,
    }
    row.style.transition = 'none'
    try { row.setPointerCapture(event.pointerId) } catch { /* optional */ }
  })

  row.addEventListener('pointermove', event => {
    if (!state) return
    state.currentX = event.clientX
    const dx = event.clientX - state.startX
    const dy = event.clientY - state.startY

    if (!state.lockedHorizontal) {
      if (Math.abs(dx) < 8 && Math.abs(dy) < 8) return
      if (Math.abs(dy) > Math.abs(dx)) {
        reset()
        return
      }
      state.lockedHorizontal = true
    }

    event.preventDefault()
    const translate = Math.max(-MAX_TRANSLATE, Math.min(MAX_TRANSLATE, dx))
    row.style.transform = `translateX(${translate}px)`
  })

  row.addEventListener('pointerup', event => {
    if (!state) return
    const dx = event.clientX - state.startX
    const shouldReply = state.lockedHorizontal && Math.abs(dx) >= SWIPE_THRESHOLD
    const button = shouldReply ? replyButtonFor(row) : null
    reset()
    if (button) {
      try { navigator.vibrate?.(8) } catch { /* optional */ }
      button.click()
    }
  })

  row.addEventListener('pointercancel', reset)
  row.addEventListener('lostpointercapture', () => {
    if (state) reset()
  })
}

export function installChatSwipeReply(): void {
  const scan = () => {
    document.querySelectorAll<HTMLElement>(`[id^="${MESSAGE_PREFIX}"]`).forEach(installOnRow)
  }

  scan()
  const observer = new MutationObserver(scan)
  observer.observe(document.body, { childList: true, subtree: true })
}
