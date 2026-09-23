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

function validateMemberTargets(members: GroupMemberKeyTarget[]): void {
  if (!Array.isArray(members) || members.length === 0 || members.length > 100) {
    throw new Error('The active group member key list is invalid.')
  }

  const seen = new Set<number>()
  for (const member of members) {
    if (!Number.isInteger(member.userId) || member.userId <= 0 || seen.has(member.userId)) {
      throw new Error('The active group member key list contains an invalid or duplicate user.')
    }
    if (typeof member.publicKey !== 'string' || !member.publicKey.trim()) {
      throw new Error(`Missing public key for member ${member.userId}.`)
    }
    seen.add(member.userId)
  }
}

/**
 * Creates the initial group key on the creator's device, wraps it separately
 * for every active member (including the creator), uploads only the encrypted
 * envelopes, and stores the creator's plaintext key locally.
 *
 * The self-envelope is intentionally stored too: the server enforces exact
 * one-envelope-per-active-member coverage for every current epoch. The local
 * plaintext key remains the authoritative fast path for the provisioner.
 */
export async function provisionInitialGroupKey(
  conversationId: number,
  keyEpoch: number,
  creatorUserId: number,
  members: GroupMemberKeyTarget[],
  upload: GroupEnvelopeUploader,
): Promise<CryptoKey> {
  if (!Number.isInteger(conversationId) || conversationId <= 0) throw new Error('Invalid conversation id.')
  if (!Number.isInteger(keyEpoch) || keyEpoch < 1) throw new Error('Invalid group key epoch.')
  if (!Number.isInteger(creatorUserId) || creatorUserId <= 0) throw new Error('Invalid group creator.')
  validateMemberTargets(members)

  const creator = members.find(member => member.userId === creatorUserId)
  if (!creator) throw new Error('The creator must be included in the active member key list.')

  const { keyPair } = await getOrCreateIdentityKeyPair(creatorUserId)
  const groupKey = await createGroupConversationKey()
  const envelopes: GroupKeyEnvelope[] = []

  for (const member of members) {
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

  await upload(conversationId, envelopes)
  await storeGroupConversationKey(conversationId, keyEpoch, groupKey)
  return groupKey
}

/**
 * Rotates a group key after a membership change. The server chooses the
 * epoch; the current member elected by the client creates a fresh symmetric
 * key locally, wraps it to every active member (including itself), and keeps
 * the plaintext key locally. The server sees only envelopes.
 */
export async function provisionRotatedGroupKey(
  conversationId: number,
  keyEpoch: number,
  senderUserId: number,
  members: GroupMemberKeyTarget[],
  upload: GroupEnvelopeUploader,
): Promise<CryptoKey> {
  if (!Number.isInteger(conversationId) || conversationId <= 0) throw new Error('Invalid conversation id.')
  if (!Number.isInteger(keyEpoch) || keyEpoch < 2) throw new Error('Invalid rotated group key epoch.')
  if (!Number.isInteger(senderUserId) || senderUserId <= 0) throw new Error('Invalid key provisioner.')
  validateMemberTargets(members)

  const sender = members.find(member => member.userId === senderUserId)
  if (!sender) throw new Error('The rotating member must still be active.')

  const { keyPair } = await getOrCreateIdentityKeyPair(senderUserId)
  const groupKey = await createGroupConversationKey()
  const envelopes: GroupKeyEnvelope[] = []

  for (const member of members) {
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

  await upload(conversationId, envelopes)
  await storeGroupConversationKey(conversationId, keyEpoch, groupKey)
  return groupKey
}