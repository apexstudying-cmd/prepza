import { getOrCreateIdentityKeyPair, importPeerPublicKey } from './keys'
import { createGroupConversationKey, wrapGroupKeyForMember, type GroupKeyEnvelope } from './group'
import { storeGroupConversationKey } from './groupStore'

export type GroupMemberKeyTarget = {
  userId: number
  publicKey: string
}

export type GroupEnvelopeUploader = (
  conversationId: number,
  envelopes: GroupKeyEnvelope[],
) => Promise<void>

/**
 * Creates the initial group key on the creator's device, wraps it separately
 * for every active member, uploads only the encrypted envelopes, and stores
 * the creator's plaintext key locally.
 *
 * The creator must be included in `members`. For the creator's own envelope,
 * the helper deliberately does not manufacture a self-ECDH envelope: the
 * creator already owns the plaintext group key locally. The backend therefore
 * receives envelopes for the other members only.
 */
export async function provisionInitialGroupKey(
  conversationId: number,
  keyEpoch: number,
  creatorUserId: number,
  members: GroupMemberKeyTarget[],
  upload: GroupEnvelopeUploader,
): Promise<CryptoKey> {
  if (!Number.isInteger(conversationId) || conversationId <= 0) {
    throw new Error('Invalid conversation id.')
  }
  if (!Number.isInteger(keyEpoch) || keyEpoch < 0) {
    throw new Error('Invalid group key epoch.')
  }

  const creator = members.find(member => member.userId === creatorUserId)
  if (!creator) {
    throw new Error('The creator must be included in the active member key list.')
  }

  const { keyPair } = await getOrCreateIdentityKeyPair()
  const groupKey = await createGroupConversationKey()
  const envelopes: GroupKeyEnvelope[] = []

  for (const member of members) {
    if (member.userId === creatorUserId) continue
    if (!member.publicKey) throw new Error(`Missing public key for member ${member.userId}.`)

    const recipientPublicKey = await importPeerPublicKey(member.publicKey)
    const envelope = await wrapGroupKeyForMember(
      groupKey,
      keyPair.privateKey,
      recipientPublicKey,
      conversationId,
      creatorUserId,
      member.userId,
    )
    envelopes.push({ ...envelope, key_epoch: keyEpoch } as GroupKeyEnvelope & { key_epoch: number })
  }

  if (envelopes.length > 0) {
    await upload(conversationId, envelopes)
  }

  await storeGroupConversationKey(conversationId, keyEpoch, groupKey)
  return groupKey
}
