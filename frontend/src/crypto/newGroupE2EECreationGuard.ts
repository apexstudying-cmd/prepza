const GROUP_CREATE_PATH = '/chats'
let installed = false

function failedResponse(message: string, status = 409): Response {
  return new Response(JSON.stringify({ error: message }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/**
 * Defense-in-depth around group creation.
 *
 * The E2EE bridge performs provisioning after the backend creates a group.
 * If provisioning cannot complete, returning the successful creation response
 * would make the UI silently enter a legacy/plaintext group. This guard turns
 * that failure into an explicit client-visible error instead.
 *
 * Existing/reused conversations are intentionally untouched because legacy
 * groups may legitimately exist from before the E2EE rollout.
 */
export function installNewGroupE2EECreationGuard(): void {
  if (installed || typeof window === 'undefined' || !window.fetch) return
  installed = true
  const nativeFetch = window.fetch.bind(window)

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const raw = typeof input === 'string' ? input : input instanceof URL ? input.pathname : input.url
    const path = new URL(raw, window.location.origin).pathname
    const method = (init?.method || (input instanceof Request ? input.method : 'GET')).toUpperCase()

    if (path !== GROUP_CREATE_PATH || method !== 'POST' || !init?.body) {
      return nativeFetch(input, init)
    }

    let payload: any
    try { payload = JSON.parse(String(init.body)) } catch { return nativeFetch(input, init) }
    const response = await nativeFetch(input, init)
    if (!response.ok || payload?.is_group !== true) return response

    const created = await response.clone().json().catch(() => null)
    if (!created?.id || created.reused !== false) return response

    const stateResponse = await nativeFetch(`/chats/${Number(created.id)}/key-envelopes`, { credentials: 'include' })
    const state = await stateResponse.json().catch(() => null)
    if (
      !stateResponse.ok ||
      state?.e2ee_mode !== 'group_v1' ||
      !Array.isArray(state?.envelopes) ||
      state.envelopes.length === 0
    ) {
      return failedResponse('Secure group setup is incomplete. No plaintext group was opened; retry after secure chat setup finishes.')
    }

    return response
  }
}
