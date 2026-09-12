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

This branch now has the end-to-end transport foundation for group study chats:

1. A random AES-256-GCM conversation key is generated on a student's device.
2. That key is wrapped separately for each active group member using the existing P-256 identity ECDH keys.
3. The server stores only encrypted key envelopes.
4. A member can fetch only their own current-epoch envelope and unwrap it locally.
5. Group messages keep the existing `body + nonce` API contract while plaintext never needs to reach the server.
6. Encrypted group search is handled locally after decryption; the server does not search message plaintext.
7. Group attachments are encrypted client-side before upload and decrypted into local blob URLs on download.
8. Group membership leaves advance the E2EE epoch; the elected active member can provision the next epoch key.
9. `key_epoch` is stamped onto group messages so historical local keys can be selected after rotation.
10. `@Ada` now has an explicit scoped endpoint/client helper. Only user-selected document text, page range and prompt are sent to the AI boundary.
11. The existing `prepza_control` bootstrap registers the E2EE chat and scoped-Ada routes after the app models are defined, so `app.py` itself does not need another competing route-registration path.

## Important production boundary

This is **not yet the final production E2EE implementation**. In particular:

- membership re-keying needs end-to-end tests for add/remove/leave races and removed-member access;
- shared-document study-reader UX is not yet wired into the chat UI, even though attachment bytes are encrypted in transit/storage;
- the current Ada document authorization is owner-only until an explicit encrypted shared-document ACL exists;
- multi-device identity/key recovery needs to be completed and tested;
- client-side encrypted search currently scans a bounded recent message window rather than maintaining a durable local index;
- device verification/key fingerprints and replay/tamper test coverage are still outstanding.

Do not market the group chat as "fully E2EE" until these lifecycle and test boundaries are verified.

## Current implementation order

### Phase 1 — text chat

- SQL migration: done on this branch
- group envelope model/routes: done
- client key generation/provisioning: done
- local message encryption/decryption: done
- epoch-aware membership handling: foundation done; tests still required

### Phase 2 — study documents

- client-side encrypted attachment bytes: done
- encrypted attachment metadata: done
- in-chat study document reader and page/selection UX: next
- explicit encrypted-document sharing/ACL model: next

### Phase 3 — collaborative Ada

The safe boundary is:

`student selects document/pages -> local plaintext selection -> explicit Ada request -> scoped AI response`

The server receives only that explicitly selected context. It does not receive the conversation history, local group key, or arbitrary private document contents.

### Phase 4 — membership and device lifecycle

- automated re-key integration tests;
- add/remove/leave concurrency tests;
- device verification/key fingerprints;
- multi-device key provisioning;
- recovery/backup UX;
- replay/tamper tests;
- large-group envelope performance tests.
