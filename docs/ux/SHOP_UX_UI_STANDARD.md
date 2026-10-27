# Prepza Shop — UX/UI and Low-Cost Frontend Standard

**Status:** Implementation guidance; Shop remains in progress and release-blocked.
**Research date:** 27 October 2026
**Applies to:** Browse/search, listing detail, create/edit listing, My Listings, Saved, payment confirmation, reporting and moderation.

## Goals

Make Shop feel like a polished, trustworthy campus marketplace without introducing infrastructure that is expensive to operate. The product is classifieds: Prepza charges sellers KES 100 per item for each 30-day listing period, including the first; renewal is manual, not an automatic recurring charge. Prepza does not process buyer purchases, hold buyer funds, provide a cart, or offer seller payouts. Buyers contact sellers directly through WhatsApp or Prepza chat.

## Research basis

- Baymard Institute, [Product Lists & Filtering UX](https://baymard.com/research/ecommerce-product-lists): scannable cards, clear price/title hierarchy, useful sorting and filtering, and understandable filter states.
- Baymard Institute, [Mobile E-commerce Usability](https://baymard.com/research/mcommerce-usability): mobile discovery, touch-friendly filters, concise product information and predictable navigation.
- Baymard Institute, [Product Page UX](https://baymard.com/research-articles/current-state-ecommerce-product-page-ux): prominent imagery, price, condition, seller context and clear next action.
- MDN, [Caching](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Caching): select a cache strategy based on the freshness and privacy requirements of the resource.
- Chrome for Developers, [Caching strategies overview](https://developer.chrome.com/docs/workbox/caching-strategies-overview): stale-while-revalidate is appropriate where immediate display matters and short-lived stale data is acceptable.
- MDN, [Cache-Control](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control): caching directives should be explicit; private or personalized data must not be treated like public static assets.

These are design principles, not a claim that a particular layout will improve conversion by a guaranteed amount. Validate with student usability tests and real device screenshots before release.

## Screen specifications

### 1. Browse and discovery

- Lead with a concise Shop heading and a clear Sell an item action. Keep the approved five Home Quick Actions; Shop occupies the former Podcasts shortcut, while Podcasts remain available from My Study. Do not add another permanent bottom-navigation item.
- Search should be easy to find and should not trigger a request on every keystroke; debounce it and preserve the current query when a user opens a detail page and returns.
- Use category, condition, location and sort controls with visible active-filter states and a one-tap clear-filters action. Avoid a large filter wall on narrow screens; use compact chips or a focused sheet/panel.
- Product cards should prioritize a consistent image ratio, short title, legible KES price, condition, location and freshness/status where available. Do not show seller-only actions to buyers.
- Use responsive grid columns only when card width remains comfortable; a single-column list is acceptable on small screens if it improves scanning and image visibility.
- Empty results should explain the situation and offer a relevant next step: clear filters or post an item. Loading states should reserve card space to reduce layout shift.
- Clearly distinguish cached results from current server results when revalidation fails; stale cards must not imply current availability or successful payment.

### 2. Listing details

- Put the image gallery and title/price near the top, followed by condition, location, description and seller identity/context.
- Make the primary actions explicit: Contact on Prepza and, when a seller supplied a valid WhatsApp contact, WhatsApp seller. These actions start a conversation; they do not purchase the item.
- Keep report listing and save/unsave actions discoverable but visually secondary. Explain safe-meeting and payment caution in concise, non-alarmist language.
- Show a visible status for paused, sold, removed or unavailable listings. Do not silently present a stale listing as definitely available.
- Avoid exposing private seller details beyond the intended contact methods and API authorization policy.

### 3. Create and edit listing

- State the price policy before the form: **KES 100 per item for each 30-day period, including your first**. Explain that this is a posting fee, not a buyer transaction or guarantee of sale.
- Keep the form in a clear order: title, category, condition, price, location, description, optional WhatsApp contact, photos, fee payment and final submission/review.
- Validate required fields inline, preserve user-entered data after recoverable errors, and prevent double-submit while uploads/payment initialization are in progress.
- Explain image types and limits before selection. Show thumbnails, upload progress, remove/retry controls, and an accurate selected-photo count. Preserve successfully uploaded image references if a later image fails, so retry does not duplicate prior uploads.
- Make payment states distinct: draft, payment pending, payment review required, paid/ready to submit, awaiting moderation, live, rejected/needs changes. Never infer payment success from the browser redirect alone; the server/provider verification remains authoritative.
- If payment status is uncertain, tell the seller to check My Listings before trying again; avoid prompting duplicate charges.
- Editing a live listing should preserve clear status and payment history. Do not charge again for an edit unless the approved business rule explicitly requires it.

### 4. My Listings and Saved

- Separate seller-owned listings from saved listings. In My Listings, show status, price, edit, pause/resume and mark-sold actions where permitted.
- Use a concise status explanation for drafts, payment review and moderation queues; give a safe recovery action instead of a dead end.
- Saved items should have an obvious unsave action and handle removed/sold listings gracefully.
- Empty states should describe how to get started without suggesting that the first listing is free.

### 5. Payment and moderation

- Treat the KES 100 fee as a 30-day listing-period fee only. There is no buyer checkout, basket, escrow, buyer-to-Prepza purchase payment, or seller payout flow.
- Verify provider callbacks/signatures and payment status on the server, make webhook handling idempotent, and ensure legacy zero-fee drafts cannot bypass payment.
- Keep moderation decisions and payment review notes separate. Only authorized admins may access moderation/payment queues.
- Provide clear report reasons, submission confirmation and a non-blocking route back to browsing. Avoid disclosing reporter information to the reported seller.

## Visual system and accessibility

- Reuse Prepza's existing design tokens, typography and navy/gold brand accents; do not introduce a parallel component system just for Shop.
- Preserve contrast in light and dark themes. Avoid low-contrast muted text on cards, buttons that rely on color alone, or tiny text for prices/statuses.
- Use semantic headings, explicit labels, keyboard-visible focus, meaningful image alt text, accessible error announcements, and touch targets around 44 CSS pixels where practical.
- Keep transitions subtle and honor reduced-motion preferences. Prefer stable skeletons and image aspect ratios to avoid content jumping.
- Test real phone and tablet widths, keyboard navigation, long titles, empty search results, large text, and network failure.

## Caching and cost policy

### Browse response

- Use a small in-memory, per-tab cache keyed by the complete normalized browse query (search, category, condition, location and sort).
- Show a recent cached browse result immediately when it is at most five minutes old, then fetch the API in the background and replace the snapshot on success.
- If revalidation fails, retain an available snapshot and show a clear stale/offline notice. The notice must not claim that a listing is still available or that a payment completed.
- Keep older snapshots only as an offline fallback; they must never override a successful fresh response.
- Invalidate or refresh relevant snapshots after listing create/edit/pause/sold, save/unsave and other mutations. If a mutation cannot be confirmed, do not optimistically present it as successful.
- Keep cache entries bounded to avoid unbounded memory growth; clear or prune older entries when practical.

### Privacy and payment boundaries

- Do not persist browse payloads containing account-specific `saved`/`is_mine` flags in localStorage, IndexedDB or a shared service-worker cache. The current in-memory cache is tab-local and deliberately avoids persistent storage.
- Do not cache `/me`, payment status/initialization, admin queues, private conversations or other account-sensitive responses in a public cache.
- A stale public listing response is a UI resilience measure, not an authoritative source for ownership, availability, moderation, or payment. Mutating actions must always be authorized and verified by the server.

### Images and object storage

- Reuse the existing R2 integration rather than introducing a new storage vendor or paid image service.
- Validate file type using content, not only extension/MIME labels; cap dimensions/size, re-encode supported raster formats, strip unnecessary metadata, and generate bounded thumbnails where the existing pipeline supports it.
- Lazy-load below-the-fold images, reserve aspect-ratio space, use appropriately sized variants, and avoid downloading full-resolution originals into card grids.
- Use long-lived caching only for immutable/versioned public image objects. If an object URL can serve private or replaceable content, choose cache headers and authorization accordingly. Confirm R2 object headers and CDN behavior in provider verification before claiming image caching is live.
- R2 cost and request usage should be monitored against the current official [R2 pricing](https://developers.cloudflare.com/r2/pricing/); do not add a separate paid cache, database, or queue just to cache a small browse result.

## Acceptance checklist

- [ ] Phone and tablet browse screens have no horizontal overflow, overlapping bottom navigation or clipped primary actions.
- [ ] Search/filter/sort cache keys are isolated; switching one filter never displays a different filter's snapshot.
- [ ] A recent cache is displayed immediately and a successful network response replaces it.
- [ ] An offline/network failure leaves a usable stale snapshot with a clear freshness warning; no snapshot means a proper error/empty state.
- [ ] Create/edit/pause/sold/save mutations invalidate or refresh affected browse snapshots.
- [ ] Account-specific flags, private responses and payment/admin data are not stored in persistent public caches.
- [ ] Product images are size-limited, lazy-loaded, correctly sized and served from existing object storage.
- [ ] Posting fee copy consistently states KES 100 per item per 30-day period including the first; no free-first-listing path exists; expired items are hidden until manual renewal.
- [ ] No cart, buyer checkout, escrow, or seller payout is shown or implemented.
- [ ] Browser regression covers browse, detail/contact, create form/photo selection, fee/payment status, moderation/reporting, offline cache fallback and mobile screenshots.
- [ ] Release tracker records the exact tested commit and remains BLOCKED until all required gates have evidence.

## Implementation status note (27 October 2026)

The Shop browse screen now has a tab-memory browse snapshot with a five-minute freshness window, background revalidation and a stale-result warning when the API fails. It is not a persistent service-worker or image-object cache. Mutation invalidation, focused automated coverage, image cache-header verification and full latest-commit browser regression must be confirmed before calling the caching work complete.

## Related documents

- [Shop architecture and business contract](../architecture/shop.md)
- [Engineering execution tracker](../NEXT_STEPS.md)
- [Release gate evidence](../../qa/release_status.json)
