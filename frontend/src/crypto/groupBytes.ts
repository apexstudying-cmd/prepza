const IV_BYTES = 12
const MAX_BYTES = 25 * 1024 * 1024

function b64(value: Uint8Array): string {
  let out = ''
  for (const byte of value) out += String.fromCharCode(byte)
  return btoa(out)
}

function unb64(value: string): Uint8Array {
  const binary = atob(value)
  const result = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) result[i] = binary.charCodeAt(i)
  return result
}

export async function encryptGroupBytes(groupKey: CryptoKey, bytes: ArrayBuffer | Uint8Array) {
  const input = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes)
  if (input.byteLength > MAX_BYTES) throw new Error('Encrypted group attachment is too large.')
  const nonce = crypto.getRandomValues(new Uint8Array(IV_BYTES))
  const ciphertext = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv: nonce },
    groupKey,
    input,
  )
  return { ciphertext, nonce: b64(nonce) }
}

export async function decryptGroupBytes(groupKey: CryptoKey, ciphertext: ArrayBuffer, nonce: string) {
  if (ciphertext.byteLength > MAX_BYTES + 16) throw new Error('Encrypted group attachment is too large.')
  const plaintext = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: unb64(nonce) },
    groupKey,
    ciphertext,
  )
  if (plaintext.byteLength > MAX_BYTES) throw new Error('Decrypted group attachment is too large.')
  return plaintext
}
