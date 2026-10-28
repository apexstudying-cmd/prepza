# Prepza Shop — End-to-End User Flow

**Status:** Implementation in progress; not release-certified.
**Last updated:** 28 October 2026.
**Commercial rule:** KES 100 per item per manually renewed 30-day listing period, including the first listing.
**Payment boundary:** Prepza collects only the seller's listing fee. Buyers pay and arrange handover directly with sellers; there is no buyer checkout, cart, escrow, or seller payout flow.

## 1. Buyer journey

1. Open **Shop** from Home's five Quick Actions. The app keeps the existing five-item bottom navigation unchanged.
2. Browse listings and use search, category, condition, campus/area, and sort filters.
3. Open a listing to inspect photos, title, KES price, condition, area, description, and seller context.
4. Choose **Message in Prepza** to start a chat, or **WhatsApp seller** if the seller supplied a valid contact number.
5. Optionally save the listing for later, or report a listing with a reason and optional details.
6. Arrange inspection, payment, and handover directly with the seller. Prepza does not collect the item's purchase price or guarantee the transaction.
7. If the listing is expired, removed, or no longer available, the server must not present it as a current public listing. A stale browse fallback is explicitly labelled as recently viewed and requires reconnection to confirm availability.

## 2. Seller listing journey

1. Open Shop and select **Sell an item**.
2. Complete title, category, condition, asking price, campus/area, description, and optional WhatsApp contact.
3. Upload at least one real product photo (JPEG, PNG, or WebP; up to six images, 5 MB each). The server validates image bytes, caps dimensions, re-encodes the image, strips EXIF/GPS metadata, and stores it under a unique object key.
4. Review the explicit fee disclosure: **KES 100 per item for each 30-day period, including your first**. There is no free first listing and no automatic recurring charge.
5. Save the draft and start the KES 100 posting-fee checkout through the configured Paystack integration. The browser redirect alone is not proof of payment; server-side provider verification controls entitlement.
6. After successful verification, the draft records the paid period. Duplicate callback/webhook delivery must not extend the same period twice or charge the seller again.
7. Select **Save & publish** / submit. The listing moves to **Awaiting review**; it is not public until an authorized moderator approves it.
8. After approval, the listing becomes **Live** and can appear in buyer browse/search results.
9. From **My listings**, the seller can inspect status, edit where allowed, pause, mark sold, remove, or resubmit after changes. Editing does not trigger a new listing fee unless the business rule changes explicitly.

## 3. Renewal and payment recovery

- The paid listing period lasts 30 days. Once expired, the listing is excluded from public browse and detail endpoints until renewed.
- Renewal is initiated manually by the seller and costs another KES 100 for the next 30-day period.
- A successful renewal restores the paid period; publishing/resubmitting still follows moderation rules.
- Duplicate or replayed success callbacks must not extend the expiry timestamp more than once.
- Invalid signatures, provider verification failures, amount/currency mismatches, or ambiguous provider results must not silently mark a listing paid. Ambiguous cases enter payment review; the seller is instructed not to retry blindly.
- Admins may resolve a payment exception only after recording provider-side verification notes for the exact reference, amount, currency, and outcome.

## 4. Moderator journey

1. An authorized admin opens **Moderation**.
2. Review listings awaiting approval and approve, reject, or remove them.
3. Review submitted reports and resolve them; removing a reported listing also removes its stored images when cleanup succeeds.
4. Review payment exceptions separately from ordinary moderation. Payment review notes and queue data are admin-only and are never included in the public browse snapshot.
5. Cache snapshots are invalidated after moderation changes so a subsequent refresh can pick up the new public state.

## 5. Browse and image caching

- Browse snapshots are held in tab memory and keyed by the complete search/filter/sort query. A recent snapshot can render immediately while the API revalidates; a failed refresh retains the same query's snapshot with a clear stale-data warning.
- Cached browse objects exclude viewer-specific `saved`/`is_mine` values and payment/moderation review details. Request sequencing prevents an older response from overwriting a newer query.
- Shop mutations invalidate snapshots where required. The cache is not an authority for payment, ownership, moderation, or availability.
- Shop image uploads set object metadata to `Cache-Control: private, max-age=86400, immutable`. Presigned GET URLs now last 86,400 seconds (24 hours), aligned with the one-day private cache window; the earlier 15-minute URL lifetime could expire before a cached image was re-used.
- The `private` directive avoids shared-cache reuse; unique image keys are treated as immutable. Browser caching is best-effort and does not guarantee image availability after local cache eviction.
- Verify actual R2 response headers, signature-expiry behavior, and upload/read/head/delete operations with safe staging credentials before claiming provider-level caching verification. No new paid cache service is introduced.

## 6. Automated evidence and remaining limits

Focused tests:
- `python -m pytest tests/test_shop_marketplace.py -q`
- `python -m pytest tests/test_shop_browse_cache_contract.py -q`
- `python -m pytest tests/test_shop_image_cache_contract.py -q`

The disposable PostgreSQL Shop journey in `tests/test_local_qa_real_world.py` covers draft creation, the KES 100 fee on first and subsequent listings, forged legacy zero-fee protection, photo validation, mocked Paystack checkout/callback verification, duplicate callback idempotency, moderation, public browse/detail, WhatsApp URL normalization, in-app chat creation, saving, reporting, expiry, manual renewal, and amount-mismatch quarantine. `scripts/test_browser_mobile_responsive.py` covers the responsive Shop surface, stale browse fallback, current fee copy, and photo-selection UI at phone/tablet viewports.

**Latest CI evidence (28 October 2026):** Shop Marketplace Contract passed on integrated code `3bc3b866` ([run 40701583898](https://github.com/apexstudying-cmd/prepza/actions/runs/40701583898)); Frontend Build passed on the same code ([run 40701583937](https://github.com/apexstudying-cmd/prepza/actions/runs/40701583937)); Release Browser and Cross-System Regression passed, including phone/tablet coverage ([run 40701583921](https://github.com/apexstudying-cmd/prepza/actions/runs/40701583921)). The documentation-only follow-up at `557daf93` also passed Frontend Build, Screen Loading Audit, Realtime Runtime Regression, E2EE Security Regression, and Student/Admin/B2B/AI/Kokoro contracts.

Mocked-provider tests are not live-provider evidence. Paystack sandbox checkout/webhook behavior and real R2 object operations/cache headers remain external-provider checks until verified with safe staging credentials. The latest-head populated-database migration rehearsal and expiry/renewal/replayed-callback evidence must be reconciled before closing those release gates. Do not use live payments, provision paid infrastructure, or start billable GPU inference without explicit approval. Keep the Shop release gate IN_PROGRESS and the overall release BLOCKED until the required current-SHA evidence and provider disposition are recorded.
