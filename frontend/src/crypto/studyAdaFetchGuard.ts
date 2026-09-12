const STUDY_ADA_RE = /^\/chats\/(\d+)\/ada\/study$/
const MAX_SELECTED_TEXT = 20_000
const MAX_PROMPT = 4_000
const MAX_PAGE_SPAN = 50

let installed = false

function failedResponse(message: string, status = 400): Response {
  return new Response(JSON.stringify({ error: message }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function pathOnly(input: RequestInfo | URL): string {
  const raw = typeof input === 'string' ? input : input instanceof URL ? input.pathname + input.search : input.url
  try {
    const url = new URL(raw, window.location.origin)
    return url.pathname
  } catch {
    return raw.split('?')[0]
  }
}

/**
 * Browser-side defense-in-depth for the explicit Ada study contract.
 *
 * The backend remains authoritative. This guard makes it impossible for a
 * normal Prepza client call to accidentally attach conversation history,
 * arbitrary document data, or unbounded text to the scoped Ada endpoint.
 */
export function installStudyAdaFetchGuard(): void {
  if (installed || typeof window === 'undefined' || !window.fetch) return
  installed = true
  const nativeFetch = window.fetch.bind(window)

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const path = pathOnly(input)
    const method = (init?.method || (input instanceof Request ? input.method : 'GET')).toUpperCase()
    const match = path.match(STUDY_ADA_RE)

    if (!match || method !== 'POST') return nativeFetch(input, init)
    if (!init?.body) return failedResponse('Ada study context is required')

    let payload: any
    try {
      payload = JSON.parse(String(init.body))
    } catch {
      return failedResponse('Ada study context must be valid JSON')
    }

    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
      return failedResponse('Ada study context must be an object')
    }
    if (payload.context_scope !== 'selected_document_pages' || payload.explicit_user_context !== true) {
      return failedResponse('Ada requires explicit selected-document context')
    }

    const conversationId = Number(match[1])
    const documentId = Number(payload.document_id)
    const keyEpoch = Number(payload.key_epoch)
    const pageStart = Number(payload.page_start)
    const pageEnd = Number(payload.page_end)

    if (!Number.isInteger(conversationId) || conversationId <= 0) return failedResponse('Invalid conversation')
    if (!Number.isInteger(documentId) || documentId <= 0) return failedResponse('Invalid study document')
    if (!Number.isInteger(keyEpoch) || keyEpoch < 1) return failedResponse('Invalid E2EE key epoch')
    if (!Number.isInteger(pageStart) || pageStart < 1 || !Number.isInteger(pageEnd) || pageEnd < pageStart) {
      return failedResponse('Invalid document page range')
    }
    if (pageEnd - pageStart + 1 > MAX_PAGE_SPAN) return failedResponse('Selected page range is too large')
    if (typeof payload.selected_text !== 'string' || payload.selected_text.length > MAX_SELECTED_TEXT) {
      return failedResponse('Selected study text is too large')
    }
    if (typeof payload.prompt !== 'string' || !payload.prompt.trim() || payload.prompt.length > MAX_PROMPT) {
      return failedResponse('Ada prompt is invalid')
    }

    // Rebuild the payload from the allowlist rather than forwarding arbitrary
    // caller-supplied fields such as conversation history, group keys, or raw
    // document contents.
    const safePayload = {
      context_scope: 'selected_document_pages',
      explicit_user_context: true,
      document_id: documentId,
      page_start: pageStart,
      page_end: pageEnd,
      key_epoch: keyEpoch,
      selected_text: payload.selected_text,
      prompt: payload.prompt,
    }

    const headers = new Headers(init.headers || {})
    if (!headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
    return nativeFetch(input, { ...init, headers, body: JSON.stringify(safePayload) })
  }
}
