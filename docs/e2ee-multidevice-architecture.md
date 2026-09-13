# Prepza E2EE multi-device architecture

## Current release boundary

Prepza currently has one E2EE identity public key per account and one private identity keypair per browser/device profile. The private key is never uploaded. The server refuses to replace an existing account identity key with a different key instead of silently orphaning existing ciphertext.

This is an explicit **single-device E2EE release boundary**. A second browser/device must not silently replace the first device's identity.

## Future multi-device protocol

Multi-device support must be added as a separate protocol version, not by changing the meaning of the current `user_key` row.

1. Add a `user_device` record with an opaque device id, public identity key, protocol version, created/revoked timestamps, and a per-device verification state.
2. Keep one identity key per device. Never overwrite a device key in place.
3. Direct-chat encryption must use a per-device recipient key set. A sender encrypts the message key for every active recipient device and for every sender device that must decrypt its own history.
4. Group key envelopes must be addressed to `(conversation, epoch, recipient_device)` rather than only `(conversation, epoch, recipient_user)`.
5. Device addition requires an authenticated device-linking ceremony; device removal revokes only that device and forces group/direct key rotation where required.
6. Existing ciphertext remains decryptable only by devices that already possess the relevant historical key. A newly linked device does not receive old group epochs automatically.
7. All new envelope formats must use a new protocol/version and authenticated metadata binding. Existing v1 ciphertext must remain readable until an intentional migration policy is chosen.

No server-side operation in the current release may request, accept, store, or reconstruct a private identity key.
