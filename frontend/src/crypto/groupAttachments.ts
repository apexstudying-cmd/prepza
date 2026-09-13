import { encryptGroupMessage } from './group'

const IV_BYTES = 12
const KEY_BYTES = 32
const MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024
const MAX_ATTACHMENT_ID = 128
const MAX_FILENAME = 255
const MAX_MIME = 128

function b64(value: ArrayBuffer | Uint8Array): string {
  const bytes = value instanceof Uint8Array ? value : new Uint8Array(value)
  let out = ''
  for (const byte of bytes) out += String.fromCharCode(byte)
  return btoa(out)
}

function unb64(value: string): Uint8Array {
  if (typeof value !== 'string' || !value || !/^[A-Za-z0-9+/]*={0,2}$/.test(value) || value.length % 4 === 1) throw new Error('Invalid encrypted attachment encoding.')
  const binary = atob(value)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
  return bytes
}

function asArrayBuffer(bytes: Uint8Array): ArrayBuffer {
  const copy = new ArrayBuffer(bytes.byteLength)
  new Uint8Array(copy).set(bytes)
  return copy
}

function assertPositiveId(value: number, label: string) {
  if (!Number.isInteger(value) || value <= 0) throw new Error(`Invalid ${label}.`)
}

function assertEpoch(value: number) {
  if (!Number.isInteger(value) || value < 1) throw new Error('Invalid group key epoch.')
}

function assertAttachmentSize(size: number) {
  if (!Number.isSafeInteger(size) || size < 0 || size > MAX_ATTACHMENT_BYTES) throw new Error('Attachment is too large for encrypted group sharing.')
}

function aad(conversationId: number, keyEpoch: number, attachmentId: string): Uint8Array {
  assertPositiveId(conversationId, 'conversation id')
  assertEpoch(keyEpoch)
  if (!attachmentId || attachmentId.length > MAX_ATTACHMENT_ID || !/^[A-Za-z0-9._-]+$/.test(attachmentId)) throw new Error('Invalid attachment id.')
  return new TextEncoder().encode(`prepza:group-attachment:v1:${conversationId}:${keyEpoch}:${attachmentId}`)
}

function validateMetadata(encrypted: EncryptedGroupAttachment) {
  if (!encrypted || encrypted.version !== 1) throw new Error('Unsupported encrypted attachment version.')
  assertPositiveId(encrypted.conversationId, 'conversation id')
  assertEpoch(encrypted.keyEpoch)
  if (!encrypted.attachmentId || encrypted.attachmentId.length > MAX_ATTACHMENT_ID || !/^[A-Za-z0-9._-]+$/.test(encrypted.attachmentId)) throw new Error('Invalid attachment id.')
  if (typeof encrypted.originalName !== 'string' || !encrypted.originalName || encrypted.originalName.length > MAX_FILENAME || /[\u0000-\u001f\u007f]/.test(encrypted.originalName)) throw new Error('Invalid attachment filename.')
  if (typeof encrypted.mimeType !== 'string' || encrypted.mimeType.length > MAX_MIME || !/^[\w.+-]+\/[\w.+-]+$/.test(encrypted.mimeType)) throw new Error('Invalid attachment MIME type.')
  assertAttachmentSize(encrypted.size)
  if (unb64(encrypted.nonce).length !== IV_BYTES) throw new Error('Invalid encrypted attachment nonce.')
  if (unb64(encrypted.ciphertext).length < encrypted.size + 16) throw new Error('Encrypted attachment ciphertext is truncated.')
  if (!encrypted.wrappedKey || !encrypted.wrappedKeyNonce) throw new Error('Encrypted attachment key wrapper is missing.')
  if (unb64(encrypted.wrappedKeyNonce).length !== IV_BYTES) throw new Error('Invalid wrapped attachment-key nonce.')
}

export type EncryptedGroupAttachment = {
  version: 1
  conversationId: number
  keyEpoch: number
  attachmentId: string
  originalName: string
  mimeType: string
  size: number
  nonce: string
  ciphertext: string
  wrappedKey: string
  wrappedKeyNonce: string
}

export async function encryptGroupAttachment(groupKey: CryptoKey, input: Blob, conversationId: number, keyEpoch: number, attachmentId: string): Promise<EncryptedGroupAttachment> {
  assertAttachmentSize(input.size)
  const safeName = input instanceof File ? input.name : 'attachment'
  if (!attachmentId || attachmentId.length > MAX_ATTACHMENT_ID || !/^[A-Za-z0-9._-]+$/.test(attachmentId)) throw new Error('Invalid attachment id.')
  if (safeName.length > MAX_FILENAME || /[\u0000-\u001f\u007f]/.test(safeName)) throw new Error('Invalid attachment filename.')
  const mimeType = input.type || 'application/octet-stream'
  if (mimeType.length > MAX_MIME || !/^[\w.+-]+\/[\w.+-]+$/.test(mimeType)) throw new Error('Invalid attachment MIME type.')
  const plaintext = await input.arrayBuffer()
  const fileKeyBytes = crypto.getRandomValues(new Uint8Array(KEY_BYTES))
  const fileKey = await crypto.subtle.importKey('raw', asArrayBuffer(fileKeyBytes), { name: 'AES-GCM' }, false, ['encrypt', 'decrypt'])
  const nonce = crypto.getRandomValues(new Uint8Array(IV_BYTES))
  const ciphertext = await crypto.subtle.encrypt({ name: 'AES-GCM', iv: asArrayBuffer(nonce), additionalData: asArrayBuffer(aad(conversationId, keyEpoch, attachmentId)) }, fileKey, plaintext)
  const wrapped = await encryptGroupMessage(groupKey, b64(fileKeyBytes))
  const result: EncryptedGroupAttachment = { version: 1, conversationId, keyEpoch, attachmentId, originalName: safeName, mimeType, size: input.size, nonce: b64(nonce), ciphertext: b64(ciphertext), wrappedKey: wrapped.body, wrappedKeyNonce: wrapped.nonce }
  validateMetadata(result)
  return result
}

export async function decryptGroupAttachment(groupKey: CryptoKey, encrypted: EncryptedGroupAttachment): Promise<Blob> {
  validateMetadata(encrypted)
  const rawKeyB64 = await decryptWrappedKey(groupKey, encrypted.wrappedKey, encrypted.wrappedKeyNonce)
  const fileKeyBytes = unb64(rawKeyB64)
  if (fileKeyBytes.byteLength !== KEY_BYTES) throw new Error('Invalid encrypted attachment key.')
  const fileKey = await crypto.subtle.importKey('raw', asArrayBuffer(fileKeyBytes), { name: 'AES-GCM' }, false, ['decrypt'])
  const plaintext = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: asArrayBuffer(unb64(encrypted.nonce)), additionalData: asArrayBuffer(aad(encrypted.conversationId, encrypted.keyEpoch, encrypted.attachmentId)) }, fileKey, asArrayBuffer(unb64(encrypted.ciphertext)))
  if (plaintext.byteLength !== encrypted.size) throw new Error('Encrypted attachment size mismatch.')
  return new Blob([plaintext], { type: encrypted.mimeType })
}

async function decryptWrappedKey(groupKey: CryptoKey, body: string, nonce: string): Promise<string> {
  const nonceBytes = unb64(nonce)
  if (nonceBytes.length !== IV_BYTES) throw new Error('Invalid wrapped attachment-key nonce.')
  const ciphertext = unb64(body)
  if (ciphertext.length < KEY_BYTES + 16) throw new Error('Wrapped attachment key is truncated.')
  const plaintext = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: asArrayBuffer(nonceBytes) }, groupKey, asArrayBuffer(ciphertext))
  return new TextDecoder().decode(plaintext)
}
