import { fetchGroupKeyEnvelopes, openGroupSession, encryptGroupText, decryptGroupText, uploadGroupKeyEnvelopes, fetchUserPublicKey } from './e2eeChatApi'
import { provisionInitialGroupKey, provisionRotatedGroupKey } from './groupProvisioning'
import { getOrCreateIdentityKeyPair, exportPublicKeyBase64Url } from './keys'
import { loadGroupConversationKey } from './groupStore'

const GROUP_MESSAGES_RE = /^\/chats\/(\d+)\/messages(?:\?.*)?$/
const GROUP_SEARCH_RE = /^\/chats\/(\d+)\/messages\/search(?:\?.*)?$/
const GROUP_CREATE_PATH = '/chats'
const GROUP_ENABLE_SUFFIX = '/enable-e2ee'
const GROUP_LEAVE_RE = /^\/chats\/(\d+)\/leave$/
const LOCAL_SEARCH_PAGE_LIMIT = 10

let installed = false
const groupReadyPromises = new Map<number, Promise<void>>()
const groupRotationPromises = new Map<string, Promise<void>>()
const groupModeCache = new Map<number, boolean>()
let identityRegistrationPromise: Promise<void> | null = null
let currentUserId: number | null = null
let currentCsrfToken = ''

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

async function provisionCurrentEpochIfElected(conversationId: number): Promise<void> {
  if (!currentUserId || !currentCsrfToken) throw new Error('Secure chat session is not ready')
  const envelopeState = await fetchGroupKeyEnvelopes(conversationId)
  if (envelopeState.e2ee_mode !== 'group_v1') throw new Error('Group E2EE is not enabled')
  if (envelopeState.envelopes.length > 0) return

  const detail = await fetchGroupDetail(conversationId)
  const activeMembers = (detail?.participants || [])
    .map((p: any) => Number(p.user_id))
    .filter((id: number) => Number.isInteger(id) && id > 0)
    .sort((a: number, b: number) => a - b)
  if (!activeMembers.length || !activeMembers.includes(currentUserId)) throw new Error('Current member is not active')
  if (activeMembers[0] !== currentUserId) throw new Error('Waiting for the elected group key provisioner')

  const rotationKey = `${conversationId}:${envelopeState.key_epoch}`
  const existing = groupRotationPromises.get(rotationKey)
  if (existing) return existing

  const promise = (async () => {
    await ensureIdentityKeyRegistered(currentCsrfToken)
    const members = await Promise.all(
      activeMembers.map(async (userId: number) => ({
        userId,
        publicKey: userId === currentUserId ? '' : await fetchUserPublicKey(userId),
      })),
    )
    await provisionRotatedGroupKey(
      conversationId,
      envelopeState.key_epoch,
      currentUserId!,
      members,
      async (id, envelopes) => uploadGroupKeyEnvelopes(id, currentCsrfToken, envelopes),
    )
  })()

  groupRotationPromises.set(rotationKey, promise)
  try {
    await promise
  } finally {
    groupRotationPromises.delete(rotationKey)
  }
}

async function openCurrentGroupSession(conversationId: number) {
  try {
    return await openGroupSession(conversationId)
  } catch {
    await provisionCurrentEpochIfElected(conversationId)
    return openGroupSession(conversationId)
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

async function decryptMessageWithEpoch(conversationId: number, message: any, currentState: { key: CryptoKey; keyEpoch: number }): Promise<any> {
  if (!message || !message.body || !message.nonce || message.is_deleted) return message
  const epoch = Number.isInteger(Number(message.key_epoch)) ? Number(message.key_epoch) : currentState.keyEpoch
  try {
    const key = epoch === currentState.keyEpoch
      ? currentState.key
      : await loadGroupConversationKey(conversationId, epoch)
    if (!key) throw new Error('Historical group key is unavailable on this device')
    return { ...message, body: await decryptGroupText(key, message.body, message.nonce) }
  } catch {
    return { ...message, body: '[Encrypted message — key unavailable on this device]' }
  }
}

async function transformGroupMessages(response: Response, conversationId: number): Promise<Response> {
  const body = await response.clone().json()
  if (!body || !Array.isArray(body.messages)) return response
  let state
  try {
    state = await openCurrentGroupSession(conversationId)
  } catch {
    const headers = new Headers(response.headers)
    headers.set('Content-Type', 'application/json')
    return new Response(JSON.stringify({ ...body, messages: body.messages.map((m: any) => ({ ...m, body: m.body ? '[Encrypted message — key unavailable on this device]' : m.body })) }), { status: response.status, statusText: response.statusText, headers })
  }
  const messages = await Promise.all(body.messages.map((message: any) => decryptMessageWithEpoch(conversationId, message, state)))
  const headers = new Headers(response.headers)
  headers.set('Content-Type', 'application/json')
  return new Response(JSON.stringify({ ...body, messages }), { status: response.status, statusText: response.statusText, headers })
}

async function transformGroupMessageResponse(response: Response, conversationId: number): Promise<Response> {
  const body = await response.clone().json()
  if (!body || !body.body || !body.nonce || body.is_deleted) return response
  try {
    const state = await openCurrentGroupSession(conversationId)
    const message = await decryptMessageWithEpoch(conversationId, body, state)
    const headers = new Headers(response.headers)
    headers.set('Content-Type', 'application/json')
    return new Response(JSON.stringify(message), { status: response.status, statusText: response.statusText, headers })
  } catch {
    return response
  }
}

async function localSearchGroupMessages(conversationId: number, query: string): Promise<Response> {
  const needle = query.trim().toLowerCase()
  if (!needle) return new Response(JSON.stringify({ messages: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } })

  const collected: any[] = []
  let beforeId: number | null = null
  for (let page = 0; page < LOCAL_SEARCH_PAGE_LIMIT; page += 1) {
    const url = beforeId == null
      ? `/chats/${conversationId}/messages`
      : `/chats/${conversationId}/messages?before_id=${beforeId}`
    const response = await window.fetch(url, { credentials: 'include' })
    if (!response.ok) return response
    const body = await response.json()
    const pageMessages = Array.isArray(body?.messages) ? body.messages : []
    collected.push(...pageMessages)
    if (pageMessages.length === 0 || pageMessages.length < 50) break
    const firstId = Number(pageMessages[0]?.id)
    if (!Number.isInteger(firstId) || firstId <= 0) break
    beforeId = firstId
  }

  const messages = collected.filter(message => typeof message?.body === 'string' && message.body.toLowerCase().includes(needle))
  return new Response(JSON.stringify({ messages: messages.slice(0, 50) }), { status: 200, headers: { 'Content-Type': 'application/json' } })
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
        if (me?.id) currentUserId = Number(me.id)
        if (me?.csrf_token) currentCsrfToken = me.csrf_token
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
          const csrfToken = csrfFrom(init.headers) || currentCsrfToken
          try { await ensureGroupProvisioned(Number(created.id), csrfToken) } catch { /* fail closed */ }
        }
      }
      return response
    }

    const searchMatch = path.match(GROUP_SEARCH_RE)
    if (searchMatch && method === 'GET') {
      const conversationId = Number(searchMatch[1])
      if (!Number.isInteger(conversationId) || conversationId <= 0) return nativeFetch(input, init)
      const enabled = await groupIsE2EE(conversationId).catch(() => false)
      if (!enabled) return nativeFetch(input, init)
      const query = new URL(path, window.location.origin).searchParams.get('q') || ''
      return localSearchGroupMessages(conversationId, query)
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
          const state = await openCurrentGroupSession(conversationId)
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
