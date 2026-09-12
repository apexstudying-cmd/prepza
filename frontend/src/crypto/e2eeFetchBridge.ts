import { openGroupSession, encryptGroupText, decryptGroupText, uploadGroupKeyEnvelopes, fetchUserPublicKey } from './e2eeChatApi'
import { provisionInitialGroupKey } from './groupProvisioning'
import { getOrCreateIdentityKeyPair, exportPublicKeyBase64Url } from './keys'

const GROUP_MESSAGES_RE = /^\/chats\/(\d+)\/messages(?:\?.*)?$/
const GROUP_CREATE_PATH = '/chats'
const GROUP_ENABLE_SUFFIX = '/enable-e2ee'
const GROUP_LEAVE_RE = /^\/chats\/(\d+)\/leave$/

let installed = false
const groupReadyPromises = new Map<number, Promise<void>>()
const groupModeCache = new Map<number, boolean>()
let identityRegistrationPromise: Promise<void> | null = null

function pathOnly(input: RequestInfo | URL): string {
  const raw = typeof input === 'string' ? input : input instanceof URL ? input.pathname + input.search : input.url
  try {
    const url = new URL(raw, window.location.origin)
    return url.pathname + url.search
  } catch {
    return raw
  }
}

function csrfFrom(headers: HeadersInit | undefined): string {
  if (!headers) return ''
  const h = new Headers(headers)
  return h.get('X-CSRF-Token') || ''
}

async function jsonClone(response: Response): Promise<any> {
  return response.clone().json()
}

async function fetchGroupDetail(conversationId: number): Promise<any> {
  const response = await window.fetch(`/chats/${conversationId}`, { credentials: 'include' })
  if (!response.ok) throw new Error(`Could not load group ${conversationId}`)
  return response.json()
}

async function ensureIdentityKeyRegistered(csrfToken: string): Promise<void> {
  if (identityRegistrationPromise) return identityRegistrationPromise

  identityRegistrationPromise = (async () => {
    const { keyPair } = await getOrCreateIdentityKeyPair()
    const publicKey = await exportPublicKeyBase64Url(keyPair.publicKey)
    const response = await window.fetch('/keys/register', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}),
      },
      body: JSON.stringify({ public_key: publicKey }),
    })
    const body = await response.json().catch(() => null)
    if (!response.ok) throw new Error((body && body.error) || 'Could not register secure chat key')
  })()

  try {
    await identityRegistrationPromise
  } catch (error) {
    identityRegistrationPromise = null
    throw error
  }
}

async function ensureGroupProvisioned(conversationId: number, csrfToken: string): Promise<void> {
  const existing = groupReadyPromises.get(conversationId)
  if (existing) return existing

  const promise = (async () => {
    await ensureIdentityKeyRegistered(csrfToken)

    const enable = await window.fetch(`/chats/${conversationId}${GROUP_ENABLE_SUFFIX}`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}),
      },
      body: '{}',
    })
    const enableBody = await enable.json().catch(() => null)
    if (!enable.ok) throw new Error((enableBody && enableBody.error) || 'Could not enable group E2EE')

    const detail = await fetchGroupDetail(conversationId)
    if (!detail?.is_group || !Array.isArray(detail.participants)) throw new Error('Conversation is not a valid group')

    const creatorUserId = Number(detail.created_by)
    if (!Number.isInteger(creatorUserId) || creatorUserId <= 0) throw new Error('Group creator is missing')

    const keyEpoch = Number(enableBody?.key_epoch)
    if (!Number.isInteger(keyEpoch) || keyEpoch < 1) throw new Error('Group E2EE key epoch is invalid')

    const members = await Promise.all(
      detail.participants
        .filter((p: any) => p && Number.isInteger(Number(p.user_id)))
        .map(async (p: any) => ({
          userId: Number(p.user_id),
          publicKey: Number(p.user_id) === creatorUserId ? '' : await fetchUserPublicKey(Number(p.user_id)),
        })),
    )

    await provisionInitialGroupKey(
      conversationId,
      keyEpoch,
      creatorUserId,
      members,
      async (id, envelopes) => uploadGroupKeyEnvelopes(id, csrfToken, envelopes),
    )
    groupModeCache.set(conversationId, true)
  })()

  groupReadyPromises.set(conversationId, promise)
  try {
    await promise
  } catch (error) {
    groupReadyPromises.delete(conversationId)
    throw error
  }
}

async function groupIsE2EE(conversationId: number): Promise<boolean> {
  const cached = groupModeCache.get(conversationId)
  if (cached !== undefined) return cached
  const response = await window.fetch(`/chats/${conversationId}/key-envelopes`, { credentials: 'include' })
  if (!response.ok) return false
  const body = await response.clone().json().catch(() => null)
  const enabled = body?.e2ee_mode === 'group_v1'
  groupModeCache.set(conversationId, enabled)
  return enabled
}

async function transformGroupMessages(response: Response, conversationId: number): Promise<Response> {
  const body = await response.clone().json()
  if (!body || !Array.isArray(body.messages)) return response
  const state = await openGroupSession(conversationId)
  const messages = await Promise.all(body.messages.map(async (message: any) => {
    if (!message || !message.body || !message.nonce || message.is_deleted) return message
    try {
      return { ...message, body: await decryptGroupText(state.key, message.body, message.nonce) }
    } catch {
      return { ...message, body: '[Encrypted message — key unavailable on this device]' }
    }
  }))
  const headers = new Headers(response.headers)
  headers.set('Content-Type', 'application/json')
  return new Response(JSON.stringify({ ...body, messages }), { status: response.status, statusText: response.statusText, headers })
}

async function transformGroupMessageResponse(response: Response, conversationId: number): Promise<Response> {
  const body = await response.clone().json()
  if (!body || !body.body || !body.nonce || body.is_deleted) return response
  const state = await openGroupSession(conversationId)
  const decrypted = await decryptGroupText(state.key, body.body, body.nonce)
  const headers = new Headers(response.headers)
  headers.set('Content-Type', 'application/json')
  return new Response(JSON.stringify({ ...body, body: decrypted }), { status: response.status, statusText: response.statusText, headers })
}

export function installE2EEFetchBridge(): void {
  if (installed || typeof window === 'undefined' || !window.fetch) return
  installed = true
  const nativeFetch = window.fetch.bind(window)

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const path = pathOnly(input)
    const method = (init?.method || (input instanceof Request ? input.method : 'GET')).toUpperCase()

    if (path === '/me' && method === 'GET') {
      const response = await nativeFetch(input, init)
      if (response.ok) {
        const me = await response.clone().json().catch(() => null)
        if (me?.id && me?.csrf_token) void ensureIdentityKeyRegistered(me.csrf_token).catch(() => {})
      }
      return response
    }

    if (path === GROUP_CREATE_PATH && method === 'POST' && init?.body) {
      let payload: any = null
      try { payload = JSON.parse(String(init.body)) } catch { /* non-JSON requests bypass */ }
      const response = await nativeFetch(input, init)
      if (payload?.is_group === true && response.ok) {
        const created = await jsonClone(response).catch(() => null)
        if (created?.id && created.reused === false) {
          const csrfToken = csrfFrom(init.headers)
          // Do not return the create response until the initial E2EE key is
          // provisioned. This closes the race where the UI could send its
          // first group message before the group had entered group_v1.
          try {
            await ensureGroupProvisioned(Number(created.id), csrfToken)
          } catch {
            // Fail closed: the group may now be marked group_v1, but no
            // plaintext message is permitted because the send path below
            // requires a local group key. The user can retry provisioning.
          }
        }
      }
      return response
    }

    const messageMatch = path.match(GROUP_MESSAGES_RE)
    if (messageMatch) {
      const conversationId = Number(messageMatch[1])
      if (!Number.isInteger(conversationId) || conversationId <= 0) return nativeFetch(input, init)

      const enabled = await groupIsE2EE(conversationId).catch(() => false)
      if (!enabled) return nativeFetch(input, init)

      if (method === 'POST' && init?.body) {
        let payload: any
        try { payload = JSON.parse(String(init.body)) } catch { return nativeFetch(input, init) }
        if (typeof payload?.body === 'string' && payload.body.trim()) {
          const state = await openGroupSession(conversationId)
          const encrypted = await encryptGroupText(state.key, payload.body)
          payload.body = encrypted.ciphertext
          payload.nonce = encrypted.nonce
          init = { ...init, body: JSON.stringify(payload) }
        }
        const response = await nativeFetch(input, init)
        return transformGroupMessageResponse(response, conversationId)
      }

      const response = await nativeFetch(input, init)
      return transformGroupMessages(response, conversationId)
    }

    if (GROUP_LEAVE_RE.test(path) && method === 'POST') return nativeFetch(input, init)
    return nativeFetch(input, init)
  }
}
