const MESSAGE_PREFIX = 'prepza-msg-'
const messageDates = new Map<number, string>()
let installed = false
let fetchInstalled = false
let scanQueued = false
let renderingDates = false
let activeConversationId: number | null = null
let pullStartY: number | null = null
let pullTriggered = false

function pathOf(input: RequestInfo | URL): string {
  const raw = typeof input === 'string' ? input : input instanceof URL ? input.pathname + input.search : input.url
  try { return new URL(raw, window.location.origin).pathname } catch { return raw.split('?')[0] }
}

function dateKey(value: string | null): string | null {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  return `${date.getFullYear()}-${date.getMonth() + 1}-${date.getDate()}`
}

function dateLabel(value: string | null): string {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const messageDay = new Date(date.getFullYear(), date.getMonth(), date.getDate())
  const days = Math.round((today.getTime() - messageDay.getTime()) / 86400000)
  if (days === 0) return 'Today'
  if (days === 1) return 'Yesterday'
  if (days >= 2 && days < 7) return date.toLocaleDateString([], { weekday: 'long' })
  return date.toLocaleDateString([], {
    day: 'numeric',
    month: 'long',
    year: date.getFullYear() === now.getFullYear() ? undefined : 'numeric',
  })
}

function requestScan() {
  if (scanQueued) return
  scanQueued = true
  requestAnimationFrame(() => {
    scanQueued = false
    scan()
  })
}

function installFetchCapture() {
  if (fetchInstalled || typeof window === 'undefined' || !window.fetch) return
  fetchInstalled = true
  const original = window.fetch.bind(window)
  window.fetch = async (input, init) => {
    const response = await original(input, init)
    const path = pathOf(input)
    const match = path.match(/^\/chats\/(\d+)\/messages(?:\?.*)?$/)
    if (match) {
      activeConversationId = Number(match[1])
      response.clone().json().then((body: unknown) => {
        const messages = Array.isArray((body as { messages?: unknown[] })?.messages)
          ? (body as { messages: unknown[] }).messages
          : []
        for (const item of messages) {
          const message = item as { id?: unknown; created_at?: unknown }
          if (Number.isInteger(message.id) && typeof message.created_at === 'string') {
            messageDates.set(message.id as number, message.created_at)
          }
        }
        requestScan()
      }).catch(() => {})
    }
    return response
  }
}

function findScrollSurface(row: HTMLElement): HTMLElement | null {
  let node: HTMLElement | null = row.parentElement
  while (node && node !== document.body) {
    const style = getComputedStyle(node)
    if ((style.overflowY === 'auto' || style.overflowY === 'scroll') && node.clientHeight <= node.scrollHeight) return node
    node = node.parentElement
  }
  return null
}

function surfaceIsDark(surface: HTMLElement): boolean {
  const background = getComputedStyle(surface).backgroundImage
  const rgb = background.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/)
  if (rgb) return 0.299 * Number(rgb[1]) + 0.587 * Number(rgb[2]) + 0.114 * Number(rgb[3]) < 150
  const color = getComputedStyle(surface).backgroundColor.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/)
  return color ? 0.299 * Number(color[1]) + 0.587 * Number(color[2]) + 0.114 * Number(color[3]) < 150 : false
}

function applyBubbleTheme(row: HTMLElement, darkMode: boolean) {
  const bubble = Array.from(row.children).find(child => child instanceof HTMLElement && child.querySelector('button[title="Reply"]')) as HTMLElement | undefined
  if (!bubble) return
  const mine = row.style.alignItems === 'flex-end'
  row.dataset.prepzaMine = mine ? '1' : '0'
  row.dataset.prepzaDark = darkMode ? '1' : '0'

  const replyButton = bubble.querySelector<HTMLButtonElement>('button[title="Reply"]')
  const reactButton = bubble.querySelector<HTMLButtonElement>('button[title="React"]')
  if (replyButton) replyButton.style.display = 'none'
  if (reactButton) reactButton.style.display = 'none'

  if (darkMode) {
    bubble.style.background = mine ? '#19345f' : '#2a2f3a'
    bubble.style.color = '#f5f7fa'
    bubble.style.borderColor = mine ? 'transparent' : '#3a414d'
  } else {
    // Light mode: keep sent and received bubbles intentionally neutral and equal.
    bubble.style.background = '#ffffff'
    bubble.style.color = '#17233f'
    bubble.style.borderColor = row.dataset.prepzaIsReply === '1' ? 'rgba(23,35,63,.55)' : 'rgba(23,35,63,.12)'
  }
  row.dataset.prepzaBubblePatched = '1'

  const quoted = bubble.querySelector<HTMLElement>('button:not([title])')
  if (quoted && quoted.textContent?.trim()) {
    quoted.style.display = 'block'
    quoted.style.minHeight = '30px'
    quoted.style.visibility = 'visible'
    quoted.style.opacity = '1'
    quoted.style.borderLeft = `3px solid ${N.gold}`
    quoted.style.background = darkMode ? 'rgba(255,255,255,.09)' : 'rgba(23,35,63,.06)'
    quoted.style.color = darkMode ? 'rgba(255,255,255,.88)' : '#17233f'
  }
}

function markReplyRows(rows: HTMLElement[]) {
  const rowById = new Map<number, HTMLElement>()
  rows.forEach(row => rowById.set(Number(row.id.slice(MESSAGE_PREFIX.length)), row))
  rows.forEach(row => {
    const bubble = Array.from(row.children).find(child => child instanceof HTMLElement && child.querySelector('button[title="React"]')) as HTMLElement | undefined
    const quoted = bubble?.querySelector<HTMLElement>('button:not([title])')
    const isReply = Boolean(quoted && quoted.textContent?.trim())
    row.dataset.prepzaIsReply = isReply ? '1' : '0'
    const target = quoted ? quoted.textContent?.trim() : ''
    if (target && !rowById.size) return
  })
}

function renderDateSeparators(surface: HTMLElement, rows: HTMLElement[]) {
  if (renderingDates) return
  renderingDates = true
  try {
    surface.querySelectorAll<HTMLElement>('[data-prepza-date-separator="1"]').forEach(node => node.remove())
    let previousKey: string | null = null
    for (const row of rows) {
      const id = Number(row.id.slice(MESSAGE_PREFIX.length))
      const createdAt = messageDates.get(id) || null
      const key = dateKey(createdAt)
      if (!key || key === previousKey) continue
      const label = dateLabel(createdAt)
      if (!label) continue

      const separator = document.createElement('div')
      separator.dataset.prepzaDateSeparator = '1'
      separator.style.cssText = 'display:flex;justify-content:center;align-items:center;margin:12px 0 8px;position:sticky;top:4px;z-index:1;pointer-events:none;'
      const chip = document.createElement('span')
      chip.textContent = label
      chip.style.cssText = 'padding:5px 10px;border-radius:10px;background:rgba(128,128,128,.16);color:inherit;font-size:10px;font-weight:800;box-shadow:0 1px 3px rgba(0,0,0,.08);backdrop-filter:blur(6px);'
      separator.appendChild(chip)
      row.before(separator)
      previousKey = key
    }
  } finally {
    renderingDates = false
  }
}

function installPullToRefresh(surface: HTMLElement) {
  if (surface.dataset.prepzaPullRefresh === '1') return
  surface.dataset.prepzaPullRefresh = '1'
  surface.addEventListener('touchstart', event => {
    if (surface.scrollTop > 2) return
    pullStartY = event.touches[0]?.clientY ?? null
    pullTriggered = false
  }, { passive: true })
  surface.addEventListener('touchmove', event => {
    if (pullStartY == null || pullTriggered || surface.scrollTop > 2) return
    const distance = (event.touches[0]?.clientY ?? pullStartY) - pullStartY
    if (distance < 72) return
    pullTriggered = true
    if (activeConversationId != null) {
      window.dispatchEvent(new CustomEvent('prepza-realtime-message', { detail: { conversation_id: activeConversationId, refresh: true } }))
    }
  }, { passive: true })
  surface.addEventListener('touchend', () => { pullStartY = null }, { passive: true })
  surface.addEventListener('touchcancel', () => { pullStartY = null }, { passive: true })
}

function scan() {
  const rows = Array.from(document.querySelectorAll<HTMLElement>(`[id^="${MESSAGE_PREFIX}"]`))
  if (!rows.length) return
  const surface = findScrollSurface(rows[0])
  if (!surface) return

  surface.classList.add('prepza-chat-scroll-surface')
  surface.style.overscrollBehaviorY = 'contain'
  surface.style.overscrollBehavior = 'contain'
  surface.style.touchAction = 'pan-y'
  installPullToRefresh(surface)
  const darkMode = surfaceIsDark(surface)
  markReplyRows(rows)
  rows.forEach(row => applyBubbleTheme(row, darkMode))
  renderDateSeparators(surface, rows)
}

function mutationContainsRealChatChange(mutations: MutationRecord[]): boolean {
  for (const mutation of mutations) {
    const nodes = [...Array.from(mutation.addedNodes), ...Array.from(mutation.removedNodes)]
    if (!nodes.length) continue
    if (nodes.some(node => !(node instanceof HTMLElement && node.closest('[data-prepza-date-separator="1"]')))) return true
  }
  return false
}

export function installChatUiPolish(): void {
  if (installed || typeof window === 'undefined') return
  installed = true
  installFetchCapture()
  scan()
  const observer = new MutationObserver(mutations => {
    if (renderingDates || !mutationContainsRealChatChange(mutations)) return
    requestScan()
  })
  observer.observe(document.body, { childList: true, subtree: true })
}
