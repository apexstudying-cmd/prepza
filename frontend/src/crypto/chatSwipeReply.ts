type SwipeState = {
  startX: number
  startY: number
  currentX: number
  lockedHorizontal: boolean
}

type LongPressState = {
  startX: number
  startY: number
  timer: number | null
  fired: boolean
}

const MESSAGE_PREFIX = 'prepza-msg-'
const SWIPE_THRESHOLD = 48
const MAX_TRANSLATE = 76
const LONG_PRESS_MS = 500
const LONG_PRESS_MOVE_TOLERANCE = 12
const REACTION_EMOJIS = ['👍', '❤️', '😂', '😮', '😢', '🙏']

function messageRow(element: EventTarget | null): HTMLElement | null {
  if (!(element instanceof HTMLElement)) return null
  const row = element.closest(`[id^="${MESSAGE_PREFIX}"]`)
  return row instanceof HTMLElement ? row : null
}

function actionButtonFor(row: HTMLElement, title: string): HTMLButtonElement | null {
  return row.querySelector<HTMLButtonElement>(`button[title="${title}"]`)
}

function closeLongPressMenu(): void {
  document.querySelectorAll<HTMLElement>('[data-prepza-longpress-menu="1"]').forEach(menu => menu.remove())
}

function showLongPressMenu(row: HTMLElement): void {
  closeLongPressMenu()
  const reactButton = actionButtonFor(row, 'React')
  const replyButton = actionButtonFor(row, 'Reply')
  if (!reactButton || !replyButton) return

  const dark = row.dataset.prepzaDark === '1'
  const menu = document.createElement('div')
  menu.dataset.prepzaLongpressMenu = '1'
  menu.style.cssText = `position:fixed;z-index:9999;display:flex;align-items:center;gap:3px;padding:5px 6px;border:1px solid ${dark ? '#3a414d' : 'rgba(23,35,63,.16)'};border-radius:18px;background:${dark ? '#242933' : 'rgba(255,255,255,.98)'};color:${dark ? '#f5f7fa' : '#17233f'};box-shadow:0 8px 28px rgba(0,0,0,.18);backdrop-filter:blur(12px);`

  REACTION_EMOJIS.forEach(emoji => {
    const button = document.createElement('button')
    button.type = 'button'
    button.textContent = emoji
    button.setAttribute('aria-label', `React ${emoji}`)
    button.style.cssText = 'border:0;background:transparent;border-radius:50%;font-size:21px;line-height:1;padding:5px;cursor:pointer;touch-action:manipulation;'
    button.addEventListener('click', event => {
      event.stopPropagation()
      closeLongPressMenu()
      reactButton.click()
      window.setTimeout(() => {
        const pickerButtons = Array.from(row.querySelectorAll<HTMLButtonElement>('button')).filter(item => item.textContent?.trim() === emoji && item !== reactButton)
        pickerButtons[0]?.click()
      }, 0)
    })
    menu.appendChild(button)
  })

  const divider = document.createElement('span')
  divider.style.cssText = 'width:1px;height:24px;background:rgba(128,128,128,.2);margin:0 3px;'
  menu.appendChild(divider)

  const reply = document.createElement('button')
  reply.type = 'button'
  reply.textContent = '↩ Reply'
  reply.style.cssText = `border:0;background:transparent;color:${dark ? '#f5f7fa' : '#17233f'};font-size:12px;font-weight:800;padding:7px 8px;border-radius:12px;cursor:pointer;white-space:nowrap;`
  reply.addEventListener('click', event => {
    event.stopPropagation()
    closeLongPressMenu()
    replyButton.click()
  })
  menu.appendChild(reply)

  document.body.appendChild(menu)
  const rect = row.getBoundingClientRect()
  const menuRect = menu.getBoundingClientRect()
  const left = Math.min(Math.max(8, rect.left + rect.width / 2 - menuRect.width / 2), window.innerWidth - menuRect.width - 8)
  const top = rect.top > menuRect.height + 12 ? rect.top - menuRect.height - 8 : Math.min(window.innerHeight - menuRect.height - 8, rect.bottom + 8)
  menu.style.left = `${left}px`
  menu.style.top = `${top}px`
  try { navigator.vibrate?.(10) } catch { /* optional */ }
}

function installOnRow(row: HTMLElement): void {
  if (row.dataset.prepzaSwipeReply === '3') return
  row.dataset.prepzaSwipeReply = '3'
  row.style.touchAction = 'pan-y'
  row.style.willChange = 'transform'

  let swipe: SwipeState | null = null
  let longPress: LongPressState | null = null

  const clearLongPress = () => {
    if (longPress?.timer != null) window.clearTimeout(longPress.timer)
    longPress = null
  }

  const resetSwipe = () => {
    swipe = null
    row.style.transition = 'transform 140ms ease-out'
    row.style.transform = ''
  }

  row.addEventListener('pointerdown', event => {
    if (event.pointerType === 'mouse' && event.button !== 0) return
    closeLongPressMenu()
    swipe = { startX: event.clientX, startY: event.clientY, currentX: event.clientX, lockedHorizontal: false }
    longPress = { startX: event.clientX, startY: event.clientY, timer: null, fired: false }
    row.style.transition = 'none'
    try { row.setPointerCapture(event.pointerId) } catch { /* optional */ }
    longPress.timer = window.setTimeout(() => {
      if (!longPress) return
      longPress.fired = true
      resetSwipe()
      showLongPressMenu(row)
    }, LONG_PRESS_MS)
  })

  row.addEventListener('pointermove', event => {
    if (!swipe) return
    swipe.currentX = event.clientX
    const dx = event.clientX - swipe.startX
    const dy = event.clientY - swipe.startY

    if (longPress && (Math.abs(dx) > LONG_PRESS_MOVE_TOLERANCE || Math.abs(dy) > LONG_PRESS_MOVE_TOLERANCE)) clearLongPress()
    if (longPress?.fired) return

    if (!swipe.lockedHorizontal) {
      if (Math.abs(dx) < 8 && Math.abs(dy) < 8) return
      if (Math.abs(dy) > Math.abs(dx)) {
        clearLongPress()
        resetSwipe()
        return
      }
      swipe.lockedHorizontal = true
    }

    event.preventDefault()
    const translate = Math.max(-MAX_TRANSLATE, Math.min(MAX_TRANSLATE, dx))
    row.style.transform = `translateX(${translate}px)`
  })

  row.addEventListener('pointerup', event => {
    if (!swipe) return
    const wasLongPress = Boolean(longPress?.fired)
    clearLongPress()
    const dx = event.clientX - swipe.startX
    const shouldReply = !wasLongPress && swipe.lockedHorizontal && Math.abs(dx) >= SWIPE_THRESHOLD
    const button = shouldReply ? actionButtonFor(row, 'Reply') : null
    resetSwipe()
    if (button) {
      try { navigator.vibrate?.(8) } catch { /* optional */ }
      button.click()
    }
  })

  row.addEventListener('pointercancel', () => { clearLongPress(); resetSwipe() })
  row.addEventListener('lostpointercapture', () => { if (swipe) { clearLongPress(); resetSwipe() } })
}

export function installChatSwipeReply(): void {
  const scan = () => document.querySelectorAll<HTMLElement>(`[id^="${MESSAGE_PREFIX}"]`).forEach(installOnRow)
  scan()
  const observer = new MutationObserver(scan)
  observer.observe(document.body, { childList: true, subtree: true })
  document.addEventListener('pointerdown', event => {
    const target = event.target as HTMLElement | null
    if (!target?.closest('[data-prepza-longpress-menu="1"]')) closeLongPressMenu()
  })
}
