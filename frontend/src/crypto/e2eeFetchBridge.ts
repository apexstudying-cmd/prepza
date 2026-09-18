import { fetchGroupKeyEnvelopes, openGroupSession, encryptGroupText, decryptGroupText, uploadGroupKeyEnvelopes, fetchUserPublicKey } from './e2eeChatApi'
import { encryptGroupBytes, decryptGroupBytes } from './group'
import { provisionInitialGroupKey, provisionRotatedGroupKey } from './groupProvisioning'
import { getOrCreateIdentityKeyPair, exportPublicKeyBase64Url } from './keys'
import { loadGroupConversationKey } from './groupStore'

const GROUP_MESSAGES_RE = /^\/chats\/(\d+)\/messages(?:\?.*)?$/
const GROUP_SEARCH_RE = /^\/chats\/(\d+)\/messages\/search(?:\?.*)?$/
const CHAT_ATTACHMENT_CREATE_RE = /^\/chats\/(\d+)\/attachments$/
const GROUP_CREATE_PATH = '/chats'
const GROUP_ENABLE_SUFFIX = '/enable-e2ee'
const GROUP_LEAVE_RE = /^\/chats\/(\d+)\/leave$/
const LOCAL_SEARCH_PAGE_LIMIT = 10
const ENCRYPTED_ATTACHMENT_MARKER = '__prepza_e2ee_attachment_v1'

type PendingUpload = {
  conversationId: number
  attachmentId: number
  key: CryptoKey
  keyEpoch: number
  mimeType: string
}

type EncryptedAttachmentMeta = PendingUpload & { fileNonce: string }

let installed = false
const groupReadyPromises = new Map<number, Promise<void>>()
const groupRotationPromises = new Map<string, Promise<void>>()
const groupModeCache = new Map<number, boolean>()
const pendingUploads = new Map<string, PendingUpload>()
const blockedUploadUrls = new Set<string>()
const pendingAttachmentMeta = new Map<number, EncryptedAttachmentMeta>()
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

function absoluteUrl(input: RequestInfo | URL): string {
  const raw = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
  try { return new URL(raw, window.location.origin).href } catch { return raw }
}

function csrfFrom(headers: HeadersInit | undefined): string {
  if (!headers) return ''
  const h = new Headers(headers)
  return h.get('X-CSRF-Token') || ''
}

function mimeTypeFor(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase() || ''
  const map: Record<string, string> = {
    jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png',
    pdf: 'application/pdf', doc: 'application/msword',
    docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    ppt: 'application/vnd.ms-powerpoint',
    pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    webm: 'audio/webm', ogg: 'audio/ogg', mp3: 'audio/mpeg', m4a: 'audio/mp4', wav: 'audio/wav', aac: 'audio/aac', mp4: 'audio/mp4',
  }
  return map[ext] || 'application/octet-stream'
}

function failedResponse(message: string, status = 409): Response {
  return new Response(JSON.stringify({ error: message }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
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
    const body: any = await response.json().catch(() => null)
    if (!response.ok) throw new Error((body && body.error) || 'Could not register secure chat key')
  })()
  try { await identityRegistrationPromise } catch (error) { identityRegistrationPromise = null; throw error }
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
          publicKey: await fetchUserPublicKey(Number(p.user_id)),
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
  try { await promise } catch (error) { groupReadyPromises.delete(conversationId); throw error }
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
    const members = await Promise.all(activeMembers.map(async (userId: number) => ({
      userId,
      publicKey: await fetchUserPublicKey(userId),
    })))
    await provisionRotatedGroupKey(
      conversationId,
      envelopeState.key_epoch,
      currentUserId!,
      members,
      async (id, envelopes) => uploadGroupKeyEnvelopes(id, currentCsrfToken, envelopes),
    )
  })()
  groupRotationPromises.set(rotationKey, promise)
  try { await promise } finally { groupRotationPromises.delete(rotationKey) }
}

async function openCurrentGroupSession(conversationId: number) {
  try { return await openGroupSession(conversationId) }
  catch {
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
    const key = epoch === currentState.keyEpoch ? currentState.key : await loadGroupConversationKey(conversationId, epoch)
    if (!key) throw new Error('Historical group key is unavailable on this device')
    return { ...message, body: await decryptGroupText(key, message.body, message.nonce, conversationId, epoch) }
  } catch {
    return { ...message, body: '[Encrypted message — key unavailable on this device]' }
  }
}

async function hydrateEncryptedAttachment(conversationId: number, message: any, currentState: { key: CryptoKey; keyEpoch: number }): Promise<any> {
  if (!message?.attachment || !message?.body || message.is_deleted) return message
  let metadata: any
  try { metadata = JSON.parse(message.body) } catch { return message }
  if (metadata?.marker !== ENCRYPTED_ATTACHMENT_MARKER) return message

  const attachmentConversationId = Number(metadata.conversation_id)
  const attachmentEpoch = Number(metadata.key_epoch)
  if (attachmentConversationId !== conversationId || !Number.isInteger(attachmentEpoch) || attachmentEpoch < 1) {
    return { ...message, body: null, attachment: { ...message.attachment, view_url: null } }
  }
  const fileKey = attachmentEpoch === currentState.keyEpoch ? currentState.key : await loadGroupConversationKey(conversationId, attachmentEpoch)
  if (!fileKey || !metadata.file_nonce || !message.attachment.view_url) {
    return { ...message, body: null, attachment: { ...message.attachment, view_url: null } }
  }
  try {
    const encryptedResponse = await window.fetch(message.attachment.view_url, { credentials: 'include' })
    if (!encryptedResponse.ok) throw new Error('Encrypted attachment download failed')
    const encryptedBytes = await encryptedResponse.arrayBuffer()
    const plaintext = await decryptGroupBytes(fileKey, encryptedBytes, metadata.file_nonce, conversationId, attachmentEpoch)
    const blobUrl = URL.createObjectURL(new Blob([plaintext], { type: metadata.mime_type || 'application/octet-stream' }))
    return { ...message, body: null, attachment: { ...message.attachment, view_url: blobUrl } }
  } catch {
    return { ...message, body: null, attachment: { ...message.attachment, view_url: null } }
  }
}

async function transformGroupMessages(response: Response, conversationId: number): Promise<Response> {
  const body = await response.clone().json()
  if (!body || !Array.isArray(body.messages)) return response
  let state
  try { state = await openCurrentGroupSession(conversationId) } catch {
    const headers = new Headers(response.headers)
    headers.set('Content-Type', 'application/json')
    return new Response(JSON.stringify({ ...body, messages: body.messages.map((m: any) => ({ ...m, body: m.body ? '[Encrypted message — key unavailable on this device]' : m.body })) }), { status: response.status, statusText: response.statusText, headers })
  }
  const decrypted = await Promise.all(body.messages.map((message: any) => decryptMessageWithEpoch(conversationId, message, state)))
  const hydrated = await Promise.all(decrypted.map((message: any) => hydrateEncryptedAttachment(conversationId, message, state)))
  const headers = new Headers(response.headers)
  headers.set('Content-Type', 'application/json')
  return new Response(JSON.stringify({ ...body, messages: hydrated }), { status: response.status, statusText: response.statusText, headers })
}

async function transformGroupMessageResponse(response: Response, conversationId: number): Promise<Response> {
  const body = await response.clone().json()
  if (!body || !body.body || !body.nonce || body.is_deleted) return response
  try {
    const state = await openCurrentGroupSession(conversationId)
    const decrypted = await decryptMessageWithEpoch(conversationId, body, state)
    const hydrated = await hydrateEncryptedAttachment(conversationId, decrypted, state)
    const headers = new Headers(response.headers)
    headers.set('Content-Type', 'application/json')
    return new Response(JSON.stringify(hydrated), { status: response.status, statusText: response.statusText, headers })
  } catch { return response }
}

async function localSearchGroupMessages(conversationId: number, query: string): Promise<Response> {
  const needle = query.trim().toLowerCase()
  if (!needle) return new Response(JSON.stringify({ messages: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } })
  const collected: any[] = []
  let beforeId: number | null = null
  for (let page = 0; page < LOCAL_SEARCH_PAGE_LIMIT; page += 1) {
    const url: string = beforeId == null ? `/chats/${conversationId}/messages` : `/chats/${conversationId}/messages?before_id=${beforeId}`
    const response: Response = await window.fetch(url, { credentials: 'include' })
    if (!response.ok) return response
    const body = await response.json()
    const pageMessages: any[] = Array.isArray(body?.messages) ? body.messages : []
    collected.push(...pageMessages)
    if (pageMessages.length === 0 || pageMessages.length < 50) break
    const firstId: number = Number(pageMessages[0]?.id)
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

    const attachmentCreateMatch = path.match(CHAT_ATTACHMENT_CREATE_RE)
    if (attachmentCreateMatch && method === 'POST' && init?.body) {
      const conversationId = Number(attachmentCreateMatch[1])
      const payload = (() => { try { return JSON.parse(String(init.body)) } catch { return null } })()
      const response = await nativeFetch(input, init)
      if (response.ok && payload?.original_filename) {
        const enabled = await groupIsE2EE(conversationId).catch(() => false)
        if (enabled) {
          let initBody: any = null
          try { initBody = await response.clone().json() } catch { /* invalid response */ }
          const attachmentId = Number(initBody?.attachment_id)
          const uploadUrl = String(initBody?.upload_url || '')
          if (Number.isInteger(attachmentId) && attachmentId > 0 && uploadUrl) {
            try {
              const state = await openCurrentGroupSession(conversationId)
              pendingUploads.set(uploadUrl, {
                conversationId,
                attachmentId,
                key: state.key,
                keyEpoch: state.keyEpoch,
                mimeType: mimeTypeFor(String(payload.original_filename)),
              })
            } catch {
              blockedUploadUrls.add(uploadUrl)
            }
          }
        }
      }
      return response
    }

    const uploadUrl = absoluteUrl(input)
    if (blockedUploadUrls.has(uploadUrl) && method === 'PUT') {
      return failedResponse('Secure attachment encryption is not ready on this device')
    }

    const pendingUpload = pendingUploads.get(uploadUrl)
    if (pendingUpload && method === 'PUT' && init?.body) {
      try {
        const plaintext = await new Response(init.body).arrayBuffer()
        const encrypted = await encryptGroupBytes(pendingUpload.key, plaintext, pendingUpload.conversationId, pendingUpload.keyEpoch)
        pendingAttachmentMeta.set(pendingUpload.attachmentId, { ...pendingUpload, fileNonce: encrypted.nonce })
        pendingUploads.delete(uploadUrl)
        return nativeFetch(input, { ...init, body: encrypted.ciphertext })
      } catch {
        pendingUploads.delete(uploadUrl)
        blockedUploadUrls.add(uploadUrl)
        return failedResponse('Secure attachment encryption failed')
      }
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
          const encrypted = await encryptGroupText(state.key, payload.body, conversationId, state.keyEpoch)
          payload.body = encrypted.body
          payload.nonce = encrypted.nonce
          init = { ...init, body: JSON.stringify(payload) }
        } else if (payload?.attachment_id != null) {
          const attachmentId = Number(payload.attachment_id)
          const meta = pendingAttachmentMeta.get(attachmentId)
          if (!meta || meta.conversationId !== conversationId) return failedResponse('Secure attachment encryption metadata is unavailable')
          const state = await openCurrentGroupSession(conversationId)
          if (state.keyEpoch !== meta.keyEpoch) return failedResponse('Secure attachment key epoch is stale; please upload again')
          const metadata = JSON.stringify({
            marker: ENCRYPTED_ATTACHMENT_MARKER,
            conversation_id: conversationId,
            key_epoch: meta.keyEpoch,
            file_nonce: meta.fileNonce,
            mime_type: meta.mimeType,
          })
          const encrypted = await encryptGroupText(state.key, metadata, conversationId, state.keyEpoch)
          payload.body = encrypted.body
          payload.nonce = encrypted.nonce
          pendingAttachmentMeta.delete(attachmentId)
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
