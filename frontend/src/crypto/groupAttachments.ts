import { encryptGroupMessage } from './group'

const IV_BYTES = 12
const KEY_BYTES = 32
const MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024

function b64(value: ArrayBuffer | Uint8Array): string {
  const bytes = value instanceof Uint8Array ? value : new Uint8Array(value)
  let out = ''
  for (const byte of bytes) out += String.fromCharCode(byte)
  return btoa(out)
}

function unb64(value: string): Uint8Array {
  const binary = atob(value)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
  return bytes
}

function assertAttachmentSize(size: number) {
  if (!Number.isInteger(size) || size < 0 || size > MAX_ATTACHMENT_BYTES) {
    throw new Error('Attachment is too large for encrypted group sharing.')
  }
}

function aad(conversationId: number, keyEpoch: number, attachmentId: string): Uint8Array {
  return new TextEncoder().encode(`prepza:group-attachment:v1:${conversationId}:${keyEpoch}:${attachmentId}`)
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

/**
 * Encrypts an attachment entirely in the browser.
 *
 * The random per-file AES key is encrypted by the current conversation key.
 * The server can therefore store the ciphertext and wrapped key, but cannot
 * recover the file without a member's local group key.
 */
export async function encryptGroupAttachment(
  groupKey: CryptoKey,
  input: Blob,
  conversationId: number,
  keyEpoch: number,
  attachmentId: string,
): Promise<EncryptedGroupAttachment> {
  assertAttachmentSize(input.size)
  if (!attachmentId || attachmentId.length > 128) throw new Error('Invalid attachment id.')

  const plaintext = new Uint8Array(await input.arrayBuffer())
  const fileKeyBytes = crypto.getRandomValues(new Uint8Array(KEY_BYTES))
  const fileKey = await crypto.subtle.importKey(
    'raw', fileKeyBytes, { name: 'AES-GCM' }, false, ['encrypt', 'decrypt'],
  )

  const nonce = crypto.getRandomValues(new Uint8Array(IV_BYTES))
  const ciphertext = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv: nonce, additionalData: aad(conversationId, keyEpoch, attachmentId) },
    fileKey,
    plaintext,
  )

  const wrapped = await encryptGroupMessage(groupKey, b64(fileKeyBytes))

  return {
    version: 1,
    conversationId,
    keyEpoch,
    attachmentId,
    originalName: input instanceof File ? input.name : 'attachment',
    mimeType: input.type || 'application/octet-stream',
    size: input.size,
    nonce: b64(nonce),
    ciphertext: b64(ciphertext),
    wrappedKey: wrapped.body,
    wrappedKeyNonce: wrapped.nonce,
  }
}

export async function decryptGroupAttachment(
  groupKey: CryptoKey,
  encrypted: EncryptedGroupAttachment,
): Promise<Blob> {
  if (encrypted.version !== 1) throw new Error('Unsupported encrypted attachment version.')
  assertAttachmentSize(encrypted.size)

  const rawKeyB64 = await decryptWrappedKey(groupKey, encrypted.wrappedKey, encrypted.wrappedKeyNonce)
  const fileKeyBytes = unb64(rawKeyB64)
  if (fileKeyBytes.byteLength !== KEY_BYTES) throw new Error('Invalid encrypted attachment key.')

  const fileKey = await crypto.subtle.importKey(
    'raw', fileKeyBytes, { name: 'AES-GCM' }, false, ['decrypt'],
  )
  const plaintext = await crypto.subtle.decrypt(
    {
      name: 'AES-GCM',
      iv: unb64(encrypted.nonce),
      additionalData: aad(encrypted.conversationId, encrypted.keyEpoch, encrypted.attachmentId),
    },
    fileKey,
    unb64(encrypted.ciphertext),
  )

  if (plaintext.byteLength !== encrypted.size) throw new Error('Encrypted attachment size mismatch.')
  return new Blob([plaintext], { type: encrypted.mimeType || 'application/octet-stream' })
}

async function decryptWrappedKey(groupKey: CryptoKey, body: string, nonce: string): Promise<string> {
  const plaintext = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: unb64(nonce) },
    groupKey,
    unb64(body),
  )
  return new TextDecoder().decode(plaintext)
}
