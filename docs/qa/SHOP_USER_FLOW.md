# Prepza Shop — End-to-End User Flow

**Status:** Buyer/seller/admin browser journeys and responsive checks passed on runtime code head `0f393bd011d6047915cbb12a15acac87f21102c0` (Release Browser 43171345717); current main `09bd1d82910d83797da2303a9f42afbd1739fbfe` is documentation-only; Paystack/R2 provider verification and same-SHA release certification remain open.
**Last updated:** 12 November 2026.
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
- Cached browse objects exclude viewer-specific `saved`/`is_mine` values and payment/moderation review details. Request sequencing prevents an older response from overwriting a newer query or replacing the cache entry after a newer request has superseded it; `tests/test_shop_browse_cache_contract.py` explicitly guards the sequencing check before cache mutation.
- Shop mutations invalidate snapshots where required. The cache is not an authority for payment, ownership, moderation, or availability.
- Shop image uploads set object metadata to `Cache-Control: private, max-age=86400, immutable`. Presigned GET URLs now last 86,400 seconds (24 hours), aligned with the one-day private cache window; the earlier 15-minute URL lifetime could expire before a cached image was re-used.
- The `private` directive avoids shared-cache reuse; unique image keys are treated as immutable. Browser caching is best-effort and does not guarantee image availability after local cache eviction.
- Verify actual R2 response headers, signature-expiry behavior, and upload/read/head/delete operations with safe staging credentials before claiming provider-level caching verification. No new paid cache service is introduced.

## 6. Automated evidence and remaining limits

Focused tests:
- `python -m pytest tests/test_shop_ux_contract.py -q` (semantic listing cards, 44px controls, active/clear filters, filtered-empty recovery and loading skeleton reachability)
- `python -m pytest tests/test_shop_marketplace.py -q`
- `python -m pytest tests/test_shop_browse_cache_contract.py -q`
- `python -m pytest tests/test_shop_image_cache_contract.py -q`

The disposable PostgreSQL Shop journey in `tests/test_local_qa_real_world.py` covers draft creation, the KES 100 fee on first and subsequent listings, forged legacy zero-fee protection, photo validation, mocked Paystack checkout/callback verification, duplicate callback idempotency, moderation, public browse/detail, WhatsApp URL normalization, in-app chat creation, saving, reporting, expiry, manual renewal, and amount-mismatch quarantine. `scripts/test_browser_mobile_responsive.py` covers the responsive Shop surface, stale browse fallback, current fee copy, and photo-selection UI at phone/tablet viewports.

**Latest CI evidence (28 October 2026):** Shop Marketplace Contract passed on `3e77f70`, including the regression that ensures superseded browse responses cannot overwrite cache snapshots ([run 40704322072](https://github.com/apexstudying-cmd/prepza/actions/runs/40704322072)). The full Release Browser and Cross-System Regression also passed on `3e77f70` ([run 40704322080](https://github.com/apexstudying-cmd/prepza/actions/runs/40704322080)), including responsive phone/tablet coverage and Shop integration journeys. Frontend Build, E2EE Security Regression, Realtime Runtime Regression, Screen Loading Audit and focused student/admin/B2B/AI/Kokoro checks passed on adjacent code/docs commits; see [build run](https://github.com/apexstudying-cmd/prepza/actions/runs/40704313178) and [security run](https://github.com/apexstudying-cmd/prepza/actions/runs/40704313130).

Mocked-provider tests are not live-provider evidence. Paystack sandbox checkout/webhook behavior and real R2 object operations/cache headers remain external-provider checks until verified with safe staging credentials. The Shop expiry/renewal/replayed-callback journey passed in the full browser regression. The populated-database migration and backup/restore rehearsal passed in [run 40712703724](https://github.com/apexstudying-cmd/prepza/actions/runs/40712703724) through Shop head `20261029_shop_period_payment`, preserving existing document data and verifying Shop tables/payment columns. A subsequent shared-streak migration advances Alembic head to `20261030_shared_study_streak`; the migration rehearsal must be rerun for that new head. This does not change the Shop-specific migration result. Do not use live payments, provision paid infrastructure, or start billable GPU inference without explicit approval. Keep the Shop release gate IN_PROGRESS and the overall release BLOCKED until the required current-SHA evidence and provider disposition are recorded.

## 7. 9–11 November 2026 — browse accessibility, recovery and responsive evidence

The first remediation pass changes only the browse presentation and interactions: listing cards are keyboard-operable semantic buttons; the navigation and back controls have 44px minimum targets; active filters expose a clear action; filtered-empty results offer a clear recovery path; and first-load browse uses stable card skeletons. The header now uses the Prepza navy/gold shell pattern. These changes preserve existing listing detail requests, seller contact actions, payment flow, API contracts and the seller fee rules.

The new `tests/test_shop_ux_contract.py` is included in the Frontend Build source-transform contract command. On exact PR #77 head `949530b97fea9df8557eddbd408f2c667130c511`, Frontend Build [run 43001890115](https://github.com/apexstudying-cmd/prepza/actions/runs/43001890115) and Release Browser/Cross-System Regression [run 43001889849](https://github.com/apexstudying-cmd/prepza/actions/runs/43001889849) passed. The latter passed phone-small (360x800), phone-standard (390x844), tablet-portrait (768x1024), B2B browser-to-ledger, full disposable PostgreSQL QA, and online/offline generated-artifact journeys. Twelve screenshots were uploaded in [artifact 13845874778](https://github.com/apexstudying-cmd/prepza/actions/runs/43001889849/artifacts/13845874778).

The screenshots were reviewed. They establish responsive rendering and bottom-nav clearance, not a visual design sign-off. Shop still looks more like a standalone mini-app than Home: its tall navy header/section-pill navigation, smaller dense typography and large listing-card image treatment are not yet harmonized with Home's card and quick-action language. The dedicated buyer/seller/admin walkthrough (detail, create/payment, My Listings, Saved, seller contact, reporting and moderation) remains open. Live Paystack sandbox and R2 provider checks also remain separate. Keep Shop IN_PROGRESS and do not mark it release-certified.


## 8. 11 November 2026 — visual consistency and role-based browser verification

The focused visual pass replaces the former rounded section-pill row with compact underline tabs on the existing navy Shop header, preserves the 44px interaction targets, reduces browse-card image/placeholder height to 124px, and increases listing price/title/metadata legibility. It retains the Prepza navy/gold palette, existing screen routes, seller fee disclosure, buyer-direct-contact boundary and fixed global navigation. Phone-small, phone-standard and tablet-portrait screenshots were captured and inspected against Home; Shop now uses a quieter, more consistent header/tab hierarchy and familiar white card surfaces. This is a source-and-screenshot consistency pass, not a substitute for a human student usability study.

A dedicated real-browser journey, `scripts/test_browser_shop_journeys.py`, now runs in the release workflow against disposable PostgreSQL:
- **Buyer:** browse listing/detail; confirm seller contact actions; save item; open Saved and confirm the listing appears; return to Browse; report with details; start in-app contact.
- **Seller:** open My listings; inspect an active listing; pause it; mark it sold; open the listing form and confirm the KES 100 / 30-day fee disclosure.
- **Admin:** approve a photo-referenced pending listing; reject a second listing; resolve the buyer report; record provider-verification notes and allow retry for an ambiguous payment review.

The approval fixture uses a synthetic object-key reference solely to exercise the server's moderation requirement. The browser journey does not upload to a real R2 bucket or invoke Paystack. The disposable PostgreSQL Shop suite continues to cover fee enforcement, mocked checkout/callback/idempotency, photo validation, renewal/expiry, ownership and moderation routes.

**Exact PR #77 evidence:** code head `76a435d91db27ca09292e20d16c31ec2b34c9884`; Frontend Build [run 43023202179](https://github.com/apexstudying-cmd/prepza/actions/runs/43023202179); Release Browser and Cross-System Regression [run 43023202418](https://github.com/apexstudying-cmd/prepza/actions/runs/43023202418). The release job passed production-image build, migrations/ledger, responsive phone/tablet checks, all three Shop role journeys, B2B browser-to-ledger, 99 PostgreSQL tests and online/offline generated-artifact replay. Screenshot artifact: [13855748767](https://github.com/apexstudying-cmd/prepza/actions/runs/43023202418/artifacts/13855748767). Sixteen of 17 workflows succeeded; StudyHub Library Flow was skipped and is not counted as a pass.

Paystack sandbox and real R2 operations/cache headers remain unverified pending safe staging credentials. Keep the Shop release gate IN_PROGRESS and the overall release BLOCKED. PR #77 has since been squash-merged to main as `48a11afa5ca9b582d656cd83030f5dfefc87e22f`; no production deployment or purchase was performed.


## 9. 12 November 2026 — merged exact-head browser and screenshot verification

The consolidated PR #77 was squash-merged to main as 48a11afa5ca9b582d656cd83030f5dfefc87e22f after exact code-head 3fcc2b3fbd9605c14c22a6b587475a779d559150 passed [Frontend Build 43024634109](https://github.com/apexstudying-cmd/prepza/actions/runs/43024634109) and [Release Browser/Cross-System Regression 43024634046](https://github.com/apexstudying-cmd/prepza/actions/runs/43024634046).

The release browser passed phone-small, phone-standard and tablet-portrait responsive checks, the dedicated buyer/seller/admin Shop journeys, B2B browser-to-ledger metering, 99 disposable PostgreSQL QA tests, online/offline Study Hub and generated-artifact replay, screenshot upload and cleanup. Buyer verifies detail, seller contact, save/Saved, report and Prepza chat. Seller verifies My Listings, pause, mark sold and the KES 100/30-day fee disclosure. Admin verifies approve/reject, report resolution and payment-review notes/retry handling.

Sixteen screenshots in artifact [13856133486](https://github.com/apexstudying-cmd/prepza/actions/runs/43024634046/artifacts/13856133486) were inspected, including Home and Shop at phone/tablet widths, listing editor, stale-cache views, buyer Saved/reported detail, seller listing detail and admin moderation. The visual review confirms a more consistent navy/gold shell, compact underline tabs, familiar white-card surfaces, 124px listing image/placeholder height, legible listing hierarchy and responsive bottom-navigation clearance. It is not a student usability study.

The admin browser fixture uses a synthetic uploaded-photo object-key reference; it does not exercise real R2. The disposable payment tests use mocked Paystack responses; they do not exercise real sandbox checkout/webhooks. The populated-database migration and custom-format backup/restore now pass in run 43171200015 through Alembic head `20261030_shared_study_streak`; the full role journey also passed on current main in run 43171345717. Keep the Shop gate IN_PROGRESS until safe staging credentials verify Paystack and R2 and the final combined release candidate is tested on one SHA. No buyer checkout/cart/escrow/payout or automatic recurring seller fee was introduced.

## 10. 12 November 2026 — current-main and database verification update

Release Browser [run 43171345717](https://github.com/apexstudying-cmd/prepza/actions/runs/43171345717) passed the buyer, seller and admin journeys on exact runtime code head `0f393bd011d6047915cbb12a15acac87f21102c0` (current main `09bd1d82910d83797da2303a9f42afbd1739fbfe` is documentation-only), along with phone-small, phone-standard and tablet-portrait responsive checks. The workflow uploaded current screenshots in artifact [13922288483](https://github.com/apexstudying-cmd/prepza/actions/runs/43171345717/artifacts/13922288483). The reviewed 16-image visual reference remains artifact [13856133486](https://github.com/apexstudying-cmd/prepza/actions/runs/43024634046/artifacts/13856133486).

The existing-database migration and PostgreSQL 17 custom-format backup/restore rehearsal passed in [run 43171200015](https://github.com/apexstudying-cmd/prepza/actions/runs/43171200015) on commit `73276018786bdaf007396c514fa0f358145138a7`. It preserved a seeded document and generated material while upgrading to `20261030_shared_study_streak`, then restored a 116-public-table backup into a separate disposable database and verified the Alembic revision and sentinel data. This closes the separate migration and backup/restore gates, but not the final one-SHA combined release gate.

Real Paystack sandbox checkout/webhooks and R2 object/header operations remain NOT_TESTED pending safe staging credentials. The KES 100 per item per manually renewed 30-day fee, direct seller contact, moderation and no-buyer-checkout model remain unchanged. Keep Shop IN_PROGRESS and release BLOCKED.
