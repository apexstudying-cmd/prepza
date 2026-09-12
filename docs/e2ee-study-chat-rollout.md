# Prepza E2EE Study Chats

## Target experience

Prepza Chats should feel like a familiar WhatsApp-style messenger, but with study-native primitives:

- 1:1 encrypted chats
- encrypted group chats
- shared study documents
- page/document context in messages
- `@Ada` in a chat or group
- replies, reactions, delivery/read state, attachments and pinned study material
- on-device message search for encrypted conversations

## Current foundation

The repository already has the 1:1 client-side AES-GCM/ECDH foundation. This branch adds the group-key protocol primitives:

1. A random AES-256-GCM conversation key is generated on a student's device.
2. That key is wrapped separately for every group member using the existing P-256 identity ECDH keys.
3. The server stores only encrypted envelopes.
4. The recipient fetches only their own envelope and unwraps it locally.
5. Group messages continue using the existing `body + nonce` message contract.
6. Server-side plaintext/ciphertext search is disabled for E2EE conversations; search must happen after local decryption.
7. `key_epoch` is present so membership changes can force a new group key.

## Important production boundary

This is **not yet the final production E2EE implementation**. In particular:

- group membership changes must re-key the group before removed members can be prevented from reading future messages;
- chat document attachments still need client-side file encryption before they can honestly be called E2EE;
- `@Ada` needs an explicit user-visible AI handoff path because Ada must receive the selected context in plaintext to answer it;
- multi-device identity/key recovery needs to be completed and tested;
- client-side encrypted search/indexing needs to be designed rather than leaking plaintext into the server.

Do not market the group chat as fully E2EE until those boundaries are wired and tested.

## Recommended implementation order

### Phase 1 — text chat

- apply the SQL migration;
- apply the backend patch;
- wire group key generation/envelope upload into group creation;
- fetch/unwrap the recipient envelope on group open;
- encrypt/decrypt group messages locally;
- add an `Encrypted` indicator in chat options.

### Phase 2 — study documents

- encrypt document bytes client-side with a random file key;
- wrap that file key for each chat member;
- store ciphertext in private storage;
- share page/document metadata as encrypted message payloads;
- open the document reader from the message while preserving chat context.

### Phase 3 — collaborative Ada

Use an explicit `@Ada` action:

`student message -> selected encrypted context -> local decrypt -> AI request -> Ada response -> encrypt response back into chat`

The product must clearly distinguish normal E2EE messages from an AI request, because server-side AI processing necessarily requires plaintext context at the AI boundary.

### Phase 4 — membership and device lifecycle

- group re-key on add/remove/leave;
- device verification/key fingerprints;
- multi-device key provisioning;
- recovery/backup UX;
- audit tests for removed-member access;
- replay/tamper tests;
- large-group envelope performance tests.
