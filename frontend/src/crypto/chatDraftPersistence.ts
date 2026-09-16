let installed = false
let activeConversationId: number | null = null
let userId: number | null = null
let observer: MutationObserver | null = null

function draftKey(conversationId: number): string {
  return `prepza-chat-draft:${userId ?? 'unknown'}:${conversationId}`
}

function currentComposer(): HTMLTextAreaElement | null {
  const textarea = document.querySelector<HTMLTextAreaElement>('.prepza-wa-composer textarea')
  return textarea || null
}

function restoreDraft(): void {
  if (activeConversationId == null) return
  const textarea = currentComposer()
  if (!textarea || textarea.value) return
  let draft = ''
  try { draft = localStorage.getItem(draftKey(activeConversationId)) || '' } catch { return }
  if (!draft) return
  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set
  setter?.call(textarea, draft)
  textarea.dispatchEvent(new Event('input', { bubbles: true }))
}

function installComposerListener(): void {
  if (document.documentElement.dataset.prepzaChatDrafts === '1') return
  document.documentElement.dataset.prepzaChatDrafts = '1'
  document.addEventListener('input', event => {
    const textarea = event.target instanceof HTMLTextAreaElement ? event.target : null
    if (!textarea || !textarea.closest('.prepza-wa-composer') || activeConversationId == null) return
    try {
      if (textarea.value) localStorage.setItem(draftKey(activeConversationId), textarea.value)
      else localStorage.removeItem(draftKey(activeConversationId))
    } catch { /* storage can be unavailable */ }
  }, true)
}

function installFetchObserver(): void {
  const original = window.fetch.bind(window)
  window.fetch = async (input, init) => {
    const response = await original(input, init)
    let raw = typeof input === 'string' ? input : input instanceof URL ? input.pathname : input.url
    try { raw = new URL(raw, window.location.origin).pathname } catch {}
    const match = raw.match(/^\/chats\/(\d+)\/messages$/)
    if (match) {
      activeConversationId = Number(match[1])
      queueMicrotask(restoreDraft)
    }
    return response
  }
}

export function installChatDraftPersistence(): void {
  if (installed || typeof window === 'undefined') return
  installed = true
  installComposerListener()
  void fetch('/me', { credentials: 'include', cache: 'no-store' })
    .then(response => response.ok ? response.json() : null)
    .then(me => { const id = Number(me?.id); if (Number.isInteger(id) && id > 0) { userId = id; restoreDraft() } })
    .catch(() => {})
  installFetchObserver()
  observer = new MutationObserver(() => restoreDraft())
  observer.observe(document.body, { childList: true, subtree: true })
}
