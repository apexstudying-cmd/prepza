import { getOrCreateIdentityKeyPair, importPeerPublicKey } from './keys'
import { unwrapGroupKey, type GroupKeyEnvelope } from './group'
import { loadGroupConversationKey, storeGroupConversationKey } from './groupStore'

export type GroupE2EEState = {
  conversationId: number
  keyEpoch: number
  e2eeMode: string
  key: CryptoKey
}

export type GroupEnvelopeFetcher = (conversationId: number) => Promise<{
  conversation_id: number
  key_epoch: number
  e2ee_mode: string
  envelopes: GroupKeyEnvelope[]
}>

export type PublicKeyResolver = (userId: number) => Promise<string>

function assertPositiveId(value: number, label: string): void {
  if (!Number.isInteger(value) || value <= 0) throw new Error(`Invalid ${label}.`)
}

function validateCurrentEnvelope(
  envelope: GroupKeyEnvelope,
  conversationId: number,
  keyEpoch: number,
  currentUserId?: number,
): void {
  if (envelope.version !== 1) throw new Error('Unsupported group key envelope version.')
  if (envelope.conversationId !== conversationId) throw new Error('Group key envelope belongs to another conversation.')
  if (envelope.key_epoch !== keyEpoch) throw new Error('Group key envelope belongs to another key epoch.')
  assertPositiveId(envelope.senderUserId, 'envelope sender')
  assertPositiveId(envelope.recipientUserId, 'envelope recipient')
  if (currentUserId !== undefined && envelope.recipientUserId !== currentUserId) {
    throw new Error('Group key envelope is not addressed to this device.')
  }
  if (typeof envelope.nonce !== 'string' || typeof envelope.ciphertext !== 'string') {
    throw new Error('Group key envelope is malformed.')
  }
}

/** Opens the current group epoch entirely on-device. Historical epochs are
 * intentionally loaded only from the local key store; a newly joined member
 * must never receive an old group key from the server. */
export async function openGroupE2EESession(
  conversationId: number,
  fetchEnvelopes: GroupEnvelopeFetcher,
  resolvePublicKey: PublicKeyResolver,
  expectedKeyEpoch?: number,
): Promise<GroupE2EEState> {
  assertPositiveId(conversationId, 'conversation id')
  if (expectedKeyEpoch !== undefined && (!Number.isInteger(expectedKeyEpoch) || expectedKeyEpoch < 1)) {
    throw new Error('Invalid expected group key epoch.')
  }

  const remote = await fetchEnvelopes(conversationId)
  if (remote.conversation_id !== conversationId) throw new Error('Group key response belongs to another conversation.')
  if (remote.e2ee_mode !== 'group_v1') throw new Error('This group is not using the supported E2EE protocol.')
  if (!Number.isInteger(remote.key_epoch) || remote.key_epoch < 1) throw new Error('Group key epoch is invalid.')
  if (expectedKeyEpoch !== undefined && remote.key_epoch !== expectedKeyEpoch) {
    throw new Error('The group key epoch changed; refresh the conversation before decrypting.')
  }
  if (!Array.isArray(remote.envelopes) || remote.envelopes.length > 1) {
    throw new Error('Unexpected number of group key envelopes.')
  }

  const cached = await loadGroupConversationKey(conversationId, remote.key_epoch)
  if (cached) {
    return { conversationId, keyEpoch: remote.key_epoch, e2eeMode: remote.e2ee_mode, key: cached }
  }

  const envelope = remote.envelopes[0]
  if (!envelope) throw new Error('No encrypted group key is available for this device.')

  const { keyPair } = await getOrCreateIdentityKeyPair()
  validateCurrentEnvelope(envelope, conversationId, remote.key_epoch)
  const senderPublicKeyBase64Url = await resolvePublicKey(envelope.senderUserId)
  const senderPublicKey = await importPeerPublicKey(senderPublicKeyBase64Url)
  const key = await unwrapGroupKey(envelope, keyPair.privateKey, senderPublicKey)
  await storeGroupConversationKey(conversationId, remote.key_epoch, key)

  return { conversationId, keyEpoch: remote.key_epoch, e2eeMode: remote.e2ee_mode, key }
}
