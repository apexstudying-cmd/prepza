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
 */
export async function provisionInitialGroupKey(
  conversationId: number,
  keyEpoch: number,
  creatorUserId: number,
  members: GroupMemberKeyTarget[],
  upload: GroupEnvelopeUploader,
): Promise<CryptoKey> {
  if (!Number.isInteger(conversationId) || conversationId <= 0) throw new Error('Invalid conversation id.')
  if (!Number.isInteger(keyEpoch) || keyEpoch < 0) throw new Error('Invalid group key epoch.')

  const creator = members.find(member => member.userId === creatorUserId)
  if (!creator) throw new Error('The creator must be included in the active member key list.')

  const { keyPair } = await getOrCreateIdentityKeyPair()
  const groupKey = await createGroupConversationKey()
  const envelopes: GroupKeyEnvelope[] = []

  for (const member of members) {
    if (member.userId === creatorUserId) continue
    if (!member.publicKey) throw new Error(`Missing public key for member ${member.userId}.`)

    const recipientPublicKey = await importPeerPublicKey(member.publicKey)
    envelopes.push(await wrapGroupKeyForMember(
      groupKey,
      keyPair.privateKey,
      recipientPublicKey,
      conversationId,
      creatorUserId,
      member.userId,
      keyEpoch,
    ))
  }

  if (envelopes.length > 0) await upload(conversationId, envelopes)
  await storeGroupConversationKey(conversationId, keyEpoch, groupKey)
  return groupKey
}

/**
 * Rotates a group key after a membership change. The server chooses the
 * epoch; the current member elected by the client creates a fresh symmetric
 * key locally, wraps it to every OTHER active member using their public key,
 * and keeps the plaintext key locally. The server sees only envelopes.
 */
export async function provisionRotatedGroupKey(
  conversationId: number,
  keyEpoch: number,
  senderUserId: number,
  members: GroupMemberKeyTarget[],
  upload: GroupEnvelopeUploader,
): Promise<CryptoKey> {
  if (!Number.isInteger(conversationId) || conversationId <= 0) throw new Error('Invalid conversation id.')
  if (!Number.isInteger(keyEpoch) || keyEpoch < 1) throw new Error('Invalid group key epoch.')

  const sender = members.find(member => member.userId === senderUserId)
  if (!sender) throw new Error('The rotating member must still be active.')

  const { keyPair } = await getOrCreateIdentityKeyPair()
  const groupKey = await createGroupConversationKey()
  const envelopes: GroupKeyEnvelope[] = []

  for (const member of members) {
    if (member.userId === senderUserId) continue
    if (!member.publicKey) throw new Error(`Missing public key for member ${member.userId}.`)

    const recipientPublicKey = await importPeerPublicKey(member.publicKey)
    envelopes.push(await wrapGroupKeyForMember(
      groupKey,
      keyPair.privateKey,
      recipientPublicKey,
      conversationId,
      senderUserId,
      member.userId,
      keyEpoch,
    ))
  }

  if (envelopes.length > 0) await upload(conversationId, envelopes)
  await storeGroupConversationKey(conversationId, keyEpoch, groupKey)
  return groupKey
}
