import {
  decryptMessageBody,
  deriveConversationKey,
  encryptMessageBody,
} from './conversation'
import { decryptGroupBytes, encryptGroupBytes } from './group'
import { exportPublicKeyBase64Url, getOrCreateIdentityKeyPair, importPeerPublicKey } from './keys'
import { ensureE2EEIdentityReady, fetchUserPublicKey } from './e2eeChatApi'

const DIRECT_MESSAGES_RE = /^\/chats\/(\d+)\/messages(?:\?.*)?$/
const DIRECT_SEARCH_RE = /^\/chats\/(\d+)\/messages\/search(?:\?.*)?$/
const DIRECT_ATTACHMENT_CREATE_RE = /^\/chats\/(\d+)\/attachments$/
const ENCRYPTED_ATTACHMENT_MARKER = '__prepza_e2ee_attachment_v1'

let installed = false
let currentUserId: number | null = null
const keyPromises = new Map<number, Promise<CryptoKey>>()
const detailPromises = new Map<number, Promise<any>>()
const pendingUploads = new Map<string, { conversationId: number; attachmentId: number; key: CryptoKey; mimeType: string }>()
const pendingAttachmentMeta = new Map<number, { conversationId: number; key: CryptoKey; mimeType: string; fileNonce: string }>()
const blockedUploadUrls = new Set<string>()

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

function mimeTypeFor(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase() || ''
  const map: Record<string, string> = {
    jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png',
    pdf: 'application/pdf', doc: 'application/msword',
    docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    ppt: 'application/vnd.ms-powerpoint',
    pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  }
  return map[ext] || 'application/octet-stream'
}

async function fetchConversationDetail(
  nativeFetch: typeof window.fetch,
  conversationId: number,
): Promise<any> {
  const existing = detailPromises.get(conversationId)
  if (existing) return existing
  const promise = (async () => {
    const response = await nativeFetch(`/chats/${conversationId}`, { credentials: 'include' })
    if (!response.ok) throw new Error('Could not load secure chat participants')
    return response.json()
  })()
  detailPromises.set(conversationId, promise)
  try {
    return await promise
  } catch (error) {
    detailPromises.delete(conversationId)
    throw error
  }
}

function peerUserId(detail: any): number {
  if (detail?.is_group === true || !Array.isArray(detail?.participants)) {
    throw new Error('This is not a direct conversation')
  }
  const participants = detail.participants
    .map((participant: any) => Number(participant?.user_id ?? participant?.id))
    .filter((id: number) => Number.isInteger(id) && id > 0)
  if (participants.length !== 2 || !currentUserId || !participants.includes(currentUserId)) {
    throw new Error('Direct conversation participants are invalid')
  }
  const peer = participants.find((id: number) => id !== currentUserId)
  if (!peer) throw new Error('Secure chat peer is missing')
  return peer
}

async function directConversationKey(
  nativeFetch: typeof window.fetch,
  conversationId: number,
): Promise<CryptoKey> {
  const existing = keyPromises.get(conversationId)
  if (existing) return existing

  const promise = (async () => {
    await ensureE2EEIdentityReady()

    const detail = await fetchConversationDetail(nativeFetch, conversationId)
    const peerId = peerUserId(detail)
    const peerPublicKey = await fetchUserPublicKey(peerId)
    const { keyPair } = await getOrCreateIdentityKeyPair()
    return deriveConversationKey(
      keyPair.privateKey,
      await importPeerPublicKey(peerPublicKey),
      conversationId,
    )
  })()
  keyPromises.set(conversationId, promise)
  try {
    return await promise
  } catch (error) {
    keyPromises.delete(conversationId)
    throw error
  }
}

function jsonResponse(response: Response, body: any): Response {
  const headers = new Headers(response.headers)
  headers.set('Content-Type', 'application/json')
  return new Response(JSON.stringify(body), {
    status: response.status,
    statusText: response.statusText,
    headers,
  })
}

async function decryptDirectAttachment(
  nativeFetch: typeof window.fetch,
  conversationId: number,
  message: any,
  key: CryptoKey,
): Promise<any> {
  if (!message?.attachment?.view_url || !message.body) return message
  let metadata: any
  try { metadata = JSON.parse(message.body) } catch { return message }
  if (metadata?.marker !== ENCRYPTED_ATTACHMENT_MARKER || !metadata.file_nonce) return message

  try {
    const encryptedResponse = await nativeFetch(message.attachment.view_url, { credentials: 'include' })
    if (!encryptedResponse.ok) throw new Error('Encrypted attachment download failed')
    const encryptedBytes = await encryptedResponse.arrayBuffer()
    const plaintext = await decryptGroupBytes(key, encryptedBytes, metadata.file_nonce)
    const blobUrl = URL.createObjectURL(new Blob([plaintext], { type: metadata.mime_type || 'application/octet-stream' }))
    return { ...message, body: null, attachment: { ...message.attachment, view_url: blobUrl } }
  } catch {
    return { ...message, body: null, attachment: { ...message.attachment, view_url: null } }
  }
}

async function decryptDirectMessage(
  nativeFetch: typeof window.fetch,
  conversationId: number,
  message: any,
): Promise<any> {
  if (!message || message.is_deleted || !message.body) return message
  if (!message.nonce) {
    return { ...message, body: '[Encrypted message — unavailable on this device]' }
  }
  try {
    const key = await directConversationKey(nativeFetch, conversationId)
    const decrypted = {
      ...message,
      body: await decryptMessageBody(key, message.body, message.nonce),
    }
    return decryptDirectAttachment(nativeFetch, conversationId, decrypted, key)
  } catch {
    return { ...message, body: '[Encrypted message — temporarily unavailable]' }
  }
}

async function transformDirectMessages(
  nativeFetch: typeof window.fetch,
  response: Response,
  conversationId: number,
): Promise<Response> {
  const body = await response.clone().json().catch(() => null)
  if (!body || !Array.isArray(body.messages)) return response
  const messages = await Promise.all(
    body.messages.map((message: any) => decryptDirectMessage(nativeFetch, conversationId, message)),
  )
  return jsonResponse(response, { ...body, messages })
}

async function transformDirectMessageResponse(
  nativeFetch: typeof window.fetch,
  response: Response,
  conversationId: number,
): Promise<Response> {
  const body = await response.clone().json().catch(() => null)
  if (!body || !body.body || !body.nonce || body.is_deleted) return response
  return jsonResponse(response, await decryptDirectMessage(nativeFetch, conversationId, body))
}

async function localSearchDirectMessages(
  nativeFetch: typeof window.fetch,
  conversationId: number,
  query: string,
): Promise<Response> {
  const needle = query.trim().toLowerCase()
  if (!needle) return new Response(JSON.stringify({ messages: [] }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })

  const response = await nativeFetch(`/chats/${conversationId}/messages`, { credentials: 'include' })
  if (!response.ok) return response
  const body = await response.json().catch(() => null)
  const rawMessages = Array.isArray(body?.messages) ? body.messages : []
  const messages = await Promise.all(rawMessages.map((message: any) => decryptDirectMessage(nativeFetch, conversationId, message)))
  return new Response(JSON.stringify({
    messages: messages.filter(message => typeof message?.body === 'string' && message.body.toLowerCase().includes(needle)).slice(0, 50),
  }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

export function installDirectChatE2EE(): void {
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
        if (me?.id) {
          currentUserId = Number(me.id)
          void ensureE2EEIdentityReady().catch(() => undefined)
        }
      }
      return response
    }

    const attachmentCreateMatch = path.match(DIRECT_ATTACHMENT_CREATE_RE)
    if (attachmentCreateMatch && method === 'POST' && init?.body) {
      const conversationId = Number(attachmentCreateMatch[1])
      const detail = await fetchConversationDetail(nativeFetch, conversationId).catch(() => null)
      if (!detail || detail.is_group === true) return nativeFetch(input, init)
      const payload = (() => { try { return JSON.parse(String(init.body)) } catch { return null } })()
      const response = await nativeFetch(input, init)
      if (response.ok && payload?.original_filename) {
        const body = await response.clone().json().catch(() => null)
        const attachmentId = Number(body?.attachment_id)
        const uploadUrl = String(body?.upload_url || '')
        if (Number.isInteger(attachmentId) && attachmentId > 0 && uploadUrl) {
          try {
            pendingUploads.set(uploadUrl, {
              conversationId,
              attachmentId,
              key: await directConversationKey(nativeFetch, conversationId),
              mimeType: mimeTypeFor(String(payload.original_filename)),
            })
          } catch {
            blockedUploadUrls.add(uploadUrl)
          }
        }
      }
      return response
    }

    const uploadUrl = absoluteUrl(input)
    if (blockedUploadUrls.has(uploadUrl) && method === 'PUT') {
      return new Response(JSON.stringify({ error: 'Secure attachment encryption is not ready on this device' }), {
        status: 409,
        headers: { 'Content-Type': 'application/json' },
      })
    }

    const pendingUpload = pendingUploads.get(uploadUrl)
    if (pendingUpload && method === 'PUT' && init?.body) {
      try {
        const plaintext = await new Response(init.body).arrayBuffer()
        const encrypted = await encryptGroupBytes(pendingUpload.key, plaintext)
        pendingAttachmentMeta.set(pendingUpload.attachmentId, {
          conversationId: pendingUpload.conversationId,
          key: pendingUpload.key,
          mimeType: pendingUpload.mimeType,
          fileNonce: encrypted.nonce,
        })
        pendingUploads.delete(uploadUrl)
        return nativeFetch(input, { ...init, body: encrypted.ciphertext })
      } catch {
        pendingUploads.delete(uploadUrl)
        blockedUploadUrls.add(uploadUrl)
        return new Response(JSON.stringify({ error: 'Secure attachment encryption failed' }), {
          status: 409,
          headers: { 'Content-Type': 'application/json' },
        })
      }
    }

    const searchMatch = path.match(DIRECT_SEARCH_RE)
    if (searchMatch && method === 'GET') {
      const conversationId = Number(searchMatch[1])
      if (!Number.isInteger(conversationId) || conversationId <= 0) return nativeFetch(input, init)
      const detail = await fetchConversationDetail(nativeFetch, conversationId).catch(() => null)
      if (!detail || detail.is_group === true) return nativeFetch(input, init)
      const query = new URL(path, window.location.origin).searchParams.get('q') || ''
      return localSearchDirectMessages(nativeFetch, conversationId, query)
    }

    const messageMatch = path.match(DIRECT_MESSAGES_RE)
    if (!messageMatch) return nativeFetch(input, init)

    const conversationId = Number(messageMatch[1])
    if (!Number.isInteger(conversationId) || conversationId <= 0) return nativeFetch(input, init)

    const detail = await fetchConversationDetail(nativeFetch, conversationId).catch(() => null)
    if (!detail || detail.is_group === true) return nativeFetch(input, init)

    if (method === 'POST' && init?.body) {
      let payload: any
      try { payload = JSON.parse(String(init.body)) } catch { return nativeFetch(input, init) }

      if (typeof payload?.body === 'string' && payload.body.trim() && !payload.nonce) {
        const key = await directConversationKey(nativeFetch, conversationId)
        const encrypted = await encryptMessageBody(key, payload.body)
        payload.body = encrypted.body
        payload.nonce = encrypted.nonce
      } else if (payload?.attachment_id != null) {
        const attachmentId = Number(payload.attachment_id)
        const meta = pendingAttachmentMeta.get(attachmentId)
        if (!meta || meta.conversationId !== conversationId) {
          return new Response(JSON.stringify({ error: 'Secure attachment encryption metadata is unavailable' }), {
            status: 409,
            headers: { 'Content-Type': 'application/json' },
          })
        }
        const key = await directConversationKey(nativeFetch, conversationId)
        const metadata = JSON.stringify({
          marker: ENCRYPTED_ATTACHMENT_MARKER,
          key_epoch: 1,
          file_nonce: meta.fileNonce,
          mime_type: meta.mimeType,
        })
        const encrypted = await encryptMessageBody(key, metadata)
        payload.body = encrypted.body
        payload.nonce = encrypted.nonce
        pendingAttachmentMeta.delete(attachmentId)
      }

      init = { ...init, body: JSON.stringify(payload) }
      const response = await nativeFetch(input, init)
      return transformDirectMessageResponse(nativeFetch, response, conversationId)
    }

    const response = await nativeFetch(input, init)
    return transformDirectMessages(nativeFetch, response, conversationId)
  }
}
