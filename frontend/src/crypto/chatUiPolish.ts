const MESSAGE_PREFIX = 'prepza-msg-'
const messageDates = new Map<number, string>()
let installed = false
let fetchInstalled = false
let scanQueued = false
let renderingDates = false

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
  queueMicrotask(() => {
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
    if (/^\/chats\/\d+\/messages(?:\?.*)?$/.test(path)) {
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
    if ((style.overflowY === 'auto' || style.overflowY === 'scroll') && node.clientHeight <= node.scrollHeight) {
      return node
    }
    node = node.parentElement
  }
  return null
}

function applyBubbleTheme(row: HTMLElement) {
  const bubble = Array.from(row.children).find(child => child instanceof HTMLElement && child.querySelector('button[title="Reply"]')) as HTMLElement | undefined
  if (!bubble) return

  const computed = getComputedStyle(bubble)
  const rgb = computed.backgroundColor.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/)
  const luminance = rgb ? 0.299 * Number(rgb[1]) + 0.587 * Number(rgb[2]) + 0.114 * Number(rgb[3]) : 255
  const darkMode = luminance < 155
  const mine = row.style.alignItems === 'flex-end'

  row.dataset.prepzaMine = mine ? '1' : '0'
  row.dataset.prepzaDark = darkMode ? '1' : '0'

  if (darkMode) {
    bubble.style.background = mine ? '#19345f' : '#2a2f3a'
    bubble.style.color = '#f5f7fa'
    bubble.style.borderColor = mine ? 'transparent' : '#3a414d'
  } else if (row.dataset.prepzaBubblePatched === '1') {
    bubble.style.background = ''
    bubble.style.color = ''
    bubble.style.borderColor = ''
  }
  row.dataset.prepzaBubblePatched = '1'
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

function scan() {
  const rows = Array.from(document.querySelectorAll<HTMLElement>(`[id^="${MESSAGE_PREFIX}"]`))
  if (!rows.length) return
  const surface = findScrollSurface(rows[0])
  if (!surface) return

  surface.classList.add('prepza-chat-scroll-surface')
  surface.style.overscrollBehaviorY = 'contain'
  surface.style.overscrollBehavior = 'contain'
  surface.style.touchAction = 'pan-y'
  rows.forEach(applyBubbleTheme)
  renderDateSeparators(surface, rows)
}

export function installChatUiPolish(): void {
  if (installed || typeof window === 'undefined') return
  installed = true
  installFetchCapture()
  scan()
  const observer = new MutationObserver(() => {
    if (!renderingDates) requestScan()
  })
  observer.observe(document.body, { childList: true, subtree: true })
}
