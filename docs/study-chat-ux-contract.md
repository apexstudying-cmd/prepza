# Prepza Study Chat UX Contract

This is the product contract for the final student chat experience. It is intentionally WhatsApp-like in interaction patterns, but Prepza-specific in study workflows.

## Core surfaces

- Chats: recent 1:1 and group conversations with unread counts, last-message preview, timestamps, mute/archive controls, pinned chats, and search.
- Conversation: compact header, back navigation, member/profile affordance, message timeline, reply/quote, reactions, attachment sheet, voice-recording affordance, mentions, and composer behavior familiar to WhatsApp users.
- Groups: group avatar/name, member count, description, shared media/documents, pinned study materials, admin controls, invite link, and group-specific notification settings.
- Study document: a document can be opened from a message and studied without leaving the conversation. Page/section context can be shared back into chat.
- Ada: `@Ada` is a first-class mention. In a document context, Ada receives only the explicitly selected document/page/section context needed for the request.

## Message behavior

- Sent, delivered, and read states should be visually clear but understated.
- Long-press/right-click exposes message actions rather than cluttering every bubble.
- Replying quotes the original message and scrolls to the source when tapped.
- Reactions are lightweight and do not create a separate message bubble.
- Attachments render as rich cards (document, image, link, audio) rather than raw URLs.
- Draft text is retained per conversation on the device.
- Optimistic sending is used with an explicit failed/retry state.
- Offline messages remain queued locally and are sent when connectivity returns.
- Search must operate on locally decrypted message content for E2EE conversations; the server must not index plaintext E2EE message bodies.

## E2EE rules

- Ordinary messages and private study documents are encrypted before leaving the device.
- Group conversation keys are epoch-based and are re-keyed when membership changes.
- A removed member must not receive future group key epochs.
- The server stores ciphertext, encrypted key envelopes, membership metadata, delivery metadata, and other routing data required to operate the service; it must not receive plaintext message bodies.
- Push notifications for E2EE messages use generic previews and never contain plaintext message content.
- Key backup/recovery is explicit and protected by a user-controlled recovery secret; server-side recovery material remains encrypted.

## Collaborative study flow

1. Student shares a document into a chat/group.
2. The document is encrypted for the conversation and rendered as a study card.
3. Members can open the document in an in-chat study viewer.
4. A selected page/section can be referenced in a message.
5. `@Ada` can be invoked against the selected context.
6. Ada responses are clearly marked as AI-generated and scoped to the requested context.
7. AI requests must never silently expose unrelated private messages or unrelated documents.

## Visual direction

- Familiar messaging hierarchy: conversation list -> message timeline -> composer.
- Premium, restrained Prepza styling rather than a copy of WhatsApp branding.
- Dense enough for real study conversations but comfortable on a phone.
- Minimal decorative UI; prioritize avatars, unread indicators, timestamps, attachment cards, and message actions.
- Mobile-first with responsive desktop two-pane behavior where appropriate.
- Skeleton/loading states and retry states are required; avoid empty placeholder screens.

## Definition of done

The chat feature is not considered complete until the E2EE implementation and the user-facing chat experience work together end-to-end: create/open conversation, send/receive encrypted messages, create/join group, membership re-keying, encrypted document sharing, document study view, `@Ada` context flow, notifications, unread/read state, reply/reaction/attachment behavior, and responsive WhatsApp-like UX.
