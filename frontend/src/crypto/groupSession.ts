import { getOrCreateIdentityKeyPair, importPeerPublicKey } from './keys'
import { unwrapGroupKey, type GroupKeyEnvelope } from './group'
import { loadGroupConversationKey, storeGroupConversationKey } from './groupStore'

export type GroupE2EEState = {
  conversationId: number
  keyEpoch: number
  e2eeMode: string
  key: CryptoKey
}

export type GroupEnvelopeFetcher = (
  conversationId: number,
) => Promise<{
  conversation_id: number
  key_epoch: number
  e2ee_mode: string
  envelopes: GroupKeyEnvelope[]
}>

export type PublicKeyResolver = (userId: number) => Promise<string>

/**
 * Opens the current group E2EE session entirely on-device.
 *
 * The server response is treated as routing material only: it contains an
 * encrypted envelope addressed to the current user. The actual group key is
 * unwrapped with the device's private identity key and then persisted locally.
 *
 * The helper intentionally takes the network functions as callbacks so the
 * crypto layer stays independent of App.tsx/fetch and can be tested in
 * isolation.
 */
export async function openGroupE2EESession(
  conversationId: number,
  fetchEnvelopes: GroupEnvelopeFetcher,
  resolvePublicKey: PublicKeyResolver,
): Promise<GroupE2EEState> {
  const remote = await fetchEnvelopes(conversationId)

  if (remote.e2ee_mode !== 'group_v1') {
    throw new Error('This group is not using the supported E2EE protocol.')
  }

  const cached = await loadGroupConversationKey(conversationId, remote.key_epoch)
  if (cached) {
    return {
      conversationId,
      keyEpoch: remote.key_epoch,
      e2eeMode: remote.e2ee_mode,
      key: cached,
    }
  }

  const envelope = remote.envelopes[0]
  if (!envelope) {
    throw new Error('No encrypted group key is available for this device.')
  }

  const { keyPair } = await getOrCreateIdentityKeyPair()
  const senderPublicKeyBase64Url = await resolvePublicKey(envelope.senderUserId)
  const senderPublicKey = await importPeerPublicKey(senderPublicKeyBase64Url)
  const key = await unwrapGroupKey(envelope, keyPair.privateKey, senderPublicKey)

  await storeGroupConversationKey(conversationId, remote.key_epoch, key)

  return {
    conversationId,
    keyEpoch: remote.key_epoch,
    e2eeMode: remote.e2ee_mode,
    key,
  }
}
