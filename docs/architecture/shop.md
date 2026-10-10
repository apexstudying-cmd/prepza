# Prepza Shop — Product, UX, and Business Model Proposal

**Status:** Proposal only — not implemented  
**Last researched:** 10 October 2026  
**Target branch:** `main`  
**Scope:** Product placement, user experience, marketplace operations, monetization, risks, and phased implementation  
**Non-goal:** This document does not authorize or implement code, schema, navigation, payment, or infrastructure changes.

## 1. Executive recommendation

Build **Prepza Shop** as a student-first campus marketplace: a place where students and approved local sellers can publish items, discover listings, and contact sellers to arrange a purchase.

Start as a **managed classifieds marketplace**, not a platform that receives and holds buyers' money. Let buyers and sellers agree on payment and delivery directly for the first validation phase, with strong safety guidance and report/block/moderation flows. This allows Prepza to test whether students will list and buy items before it assumes the complexity of checkout, refunds, seller settlement, delivery disputes, and payment-provider approval.

Plan for a later checkout phase using a payment provider's marketplace/split-settlement capabilities only after confirming Prepza's account eligibility, supported Kenyan settlement methods, seller onboarding requirements, refund/reversal handling, tax treatment, and legal responsibilities. Do not build an internal wallet or describe any payment flow as escrow without qualified legal and provider review.

The shop should be a **fourth product pillar**, alongside:
1. Student subscriptions (B2C recurring revenue).
2. Organisation plans and sponsored campaigns (B2B revenue).
3. Prepza Shop (marketplace revenue, initially low-risk listing promotion; later transaction fees if a compliant checkout is proven).

## 2. What was inspected in the current repository

Repository inspected on `main` using the GitHub-connected repository tools. Relevant current files:

- [`frontend/src/App.tsx`](https://github.com/apexstudying-cmd/prepza/blob/main/frontend/src/App.tsx) — the React/TypeScript app is currently a large single-file screen/navigation implementation. The `Screen` union includes `home`, `explore`, `chats`, `profile`, `opportunities`, `opportunity-detail`, `library`, subscription/payment screens, and other flows. `BottomNav` currently exposes Home, Explore, a central create action, Chats, and Profile.
- [`app.py`](https://github.com/apexstudying-cmd/prepza/blob/main/app.py) — Flask app entry point, database setup, authentication/security headers, and registration of existing organisation/B2B/payment-related modules.
- [`ai_economics.py`](https://github.com/apexstudying-cmd/prepza/blob/main/ai_economics.py) — existing Free/Plus/Pro student plans and AI usage limits; the Shop should not silently alter subscription entitlements.
- [`usage_billing.py`](https://github.com/apexstudying-cmd/prepza/blob/main/usage_billing.py) — existing student usage metering and organisation audience/sponsored-inventory pricing concepts. Its documented rule distinguishes organisation audience-access pricing from sponsored inventory pricing.
- [`object_storage.py`](https://github.com/apexstudying-cmd/prepza/blob/main/object_storage.py) — provider-neutral object-storage helpers with R2 target and Supabase compatibility fallback; product photos may be a fit for this boundary after access-control and image validation are designed.
- [`docs/LAUNCH_READINESS.md`](https://github.com/apexstudying-cmd/prepza/blob/main/docs/LAUNCH_READINESS.md) — notes that live Paystack checkout/webhook verification and production storage checks are deployment tasks.
- [`docs/ADMIN_ROUTE_CONTRACT.md`](https://github.com/apexstudying-cmd/prepza/blob/main/docs/ADMIN_ROUTE_CONTRACT.md) — documents route/UI contract gaps elsewhere and cautions against guessing from historical patches.
- [`docs/operations/INFRASTRUCTURE_DEPENDENCIES.md`](https://github.com/apexstudying-cmd/prepza/blob/main/docs/operations/INFRASTRUCTURE_DEPENDENCIES.md) — identifies Paystack and object storage as monitored dependencies.

### Architecture implications

1. **Do not add a new permanent bottom-navigation item in the first release.** There are already five high-value bottom-nav actions. Put Shop in Explore as a prominent first-class entry and open a dedicated Shop screen. This tests discovery without immediately making the global navigation more crowded.
2. **Keep Shop separate from Library and Study Hub.** Those are learning-material workflows; physical goods listings need prices, condition, seller information, availability, and handover details.
3. **Reuse established app boundaries only after contract inspection.** The frontend uses a central `api()` helper and screen-stack navigation. Existing chat and payment flows may be reusable, but their exact contracts must be inspected and tested before wiring Shop into them.
4. **Do not assume a marketplace backend already exists.** The inspected files establish the existing app structure, billing modules, and storage helpers; they do not prove that listing, order, seller-settlement, or marketplace-moderation tables/routes already exist.
5. **Avoid a frontend-only shop.** Listings, prices, seller ownership, moderation state, availability, and any order/payment state must be authoritative on the backend.

## 3. Product positioning and initial market

### Initial audience

Start with university students and campus-adjacent buyers/sellers in one focused pilot community. A geographically concentrated marketplace is more useful than a broad marketplace with many empty categories.

Initial candidate categories:
- Textbooks, revision guides, and permitted study supplies.
- Calculators, stationery, and small study equipment.
- Used laptops, phones, accessories, and electronics (with stricter fraud guidance).
- Dorm/hostel essentials and small household items.
- Clothing, bags, and other everyday student goods.

Do not initially allow listings for prohibited/regulated goods, counterfeit goods, weapons, medicines, alcohol, tobacco/nicotine, financial schemes, or items that breach law or university policy. Define and publish a clear prohibited-items policy before launch. Do not create a services category until safety, scope, and moderation rules are decided.

### Core promise

**“Find useful things near campus. Buy and sell with fellow students.”**

Prepza's differentiation should be campus context and trust, not trying to match every general classifieds feature:
- University/campus filters.
- Student-account identity signals without exposing private student data.
- Clear condition, price, location area, and availability.
- Fast listing creation from a phone.
- Saved listings and seller contact.
- Safety tips tailored to campus handovers.
- A clear report-listing/report-seller path.

Do not call a seller “verified” solely because they signed up with a student email. Use accurate labels such as “Prepza account” or “University email confirmed” only when that exact check has succeeded.

## 4. Where Shop belongs in the app

### Recommended navigation

- **Explore screen:** add a visible Shop entry/card near the top, alongside the existing discovery content. Use a label and short explanation rather than hiding Shop deep in a menu.
- **Dedicated Shop screen:** accessible from Explore and from Shop listing links. Keep it as a normal screen in the current navigation system, with working back-button behavior.
- **Listing detail screen:** open a listing from a product card or shared link.
- **Sell flow:** “Sell an item” button in Shop, with a clear multi-step form.
- **Profile:** add “My listings” and “My sales/inquiries” only after the backend contracts and ownership rules exist.
- **Chats:** buyer-seller contact can be integrated with existing chat only after verifying participant authorization, reporting, block behavior, and conversation creation. Otherwise, start with a safer contact-request flow instead of exposing phone numbers publicly.

Do not replace the existing Explore, Study Hub, Library, Ada, organisation discovery, or bottom-nav controls.

### Screen sketch — mobile-first

```text
┌────────────────────────────────┐
│ Shop                           │
│ Useful finds from your campus  │
│ [ Search items…            🔎 ]│
│ [Campus ▾] [Category ▾] [Sort]│
│                                │
│ [ Featured listing / banner ]  │
│                                │
│ Textbooks  Tech  Room  Fashion  │
│                                │
│ ┌────────────┐ ┌────────────┐  │
│ │ Product img│ │ Product img│  │
│ │ Textbook   │ │ Calculator │  │
│ │ KSh 450    │ │ KSh 900    │  │
│ │ Used · KU  │ │ Good · KU  │  │
│ │ [Save ♡]   │ │ [Save ♡]   │  │
│ └────────────┘ └────────────┘  │
│                                │
│ [ + Sell an item ]             │
└────────────────────────────────┘
```

This is a layout concept, not a screenshot or implementation specification. Use Prepza's existing design tokens, typography, contrast, card styles, and touch-target rules rather than introducing a separate visual system.

### Browse and listing cards

Each card should show:
- One clear primary image, with a neutral placeholder when no image exists.
- Price in KES; clearly label “Negotiable” only when the seller selected it.
- Short title and item condition.
- Campus/area (not a seller's precise location).
- Posted/updated time and listing availability.
- Save control and a clear route to detail.

Avoid cluttering cards with too many badges. “Featured” must be clearly labelled and must never imply that Prepza guarantees item quality.

### Listing detail

Display:
- Image gallery and item title.
- Price, condition, category, description, and what is included.
- Seller's public profile summary and the exact trust checks completed.
- Campus/area and seller-stated handover options.
- Availability/status.
- Primary “Contact seller” action.
- Save, share, and report actions.
- A visible safety note: inspect the item before paying; meet in a public place; do not share passwords, OTPs, or sensitive identity data; be cautious of advance-payment requests.

### Sell-an-item flow

1. Choose category.
2. Add title, description, condition, and price.
3. Add up to a small, controlled number of photos; compress on-device where possible.
4. Choose campus/area and handover method; do not publish a home address.
5. Confirm ownership/authority to sell and accept marketplace rules.
6. Preview and submit.
7. Listing enters moderation/automated checks, then becomes active or is held for review.
8. Seller can edit, mark sold, pause, or delete their listing; changes are audited.

Require title, category, price (or explicit “free”), condition, description, and area. Validate image type, size, count, and content on the server. Strip image metadata where practical. Never trust price, seller ID, moderation status, or ownership supplied by the browser.

## 5. Business model recommendation

### Phase 1: Free listings + paid visibility tests

Launch with free basic listings for early liquidity. The first business problem is marketplace density and completed buyer-seller matches, not extracting revenue from a marketplace with no activity.

Potential revenue experiments after there are active listings and repeat buyer traffic:
- **Featured listing:** test KES 50–100 for a clearly labelled 7-day boost as a pricing hypothesis, not an established market price.
- **Category/campus sponsorship:** use the existing B2B sponsored-inventory capability only if Shop placements are explicitly added to the campaign contract, reporting, targeting, and billing rules. Do not silently sell a new placement under an existing campaign type.
- **Verified business seller tools:** later offer local bookstores, repair shops, printing shops, and campus-adjacent merchants a paid storefront or listing bundle, with clear verification and renewal terms.

Keep ordinary listing creation free during the pilot. Do not charge both a seller subscription and a commission by default.

### Phase 2: Checkout and transaction revenue

Only after the pilot demonstrates demand and legal/provider checks pass:
- Introduce checkout for supported item types.
- Test a **5% seller-side marketplace fee** as an initial experiment, with the fee shown before the seller accepts it. This is a hypothesis to validate against payment costs, refund/dispute rates, and willingness to pay, not a final price.
- Do not charge a buyer fee unless research shows it is acceptable and it is clearly disclosed.
- Provide a per-order breakdown: item price, delivery (if any), provider fees where relevant, Prepza fee, and seller net amount.
- Model refunds, partial refunds, reversals, disputes, failed payments, duplicate webhook delivery, and seller payout failure before launch.

Paystack's public documentation describes split settlements through subaccounts and transaction splits, including marketplace use cases. It also documents transfers in Kenya. That does **not** establish that Prepza's merchant account, seller type, currency, mobile-money route, or proposed flow is eligible. Confirm this with Paystack before promising automatic split settlement or implementing checkout.

### Phase 3: B2B merchant layer

Offer businesses a separate seller type for approved campus-relevant merchants:
- Business storefront with contact and operating area.
- Paid featured inventory and sponsored placements.
- Aggregate listing views, contact clicks, saves, and sales where reliable event data exists.
- Optional monthly seller tools only after there is demonstrated business demand.

Keep organisation subscriptions and Shop merchant tools distinct:
- Organisation subscription buys organisation/discovery capabilities and access under its existing plan contract.
- Sponsored campaign buys a defined advertising placement and delivery.
- Shop seller tools buy marketplace-specific storefront/listing capabilities.
- A transaction fee applies only to an actual transaction processed under a documented checkout flow.

Do not bundle Shop into student Plus/Pro as a default entitlement. Subscription tiers should continue to be about study functionality unless later evidence supports a deliberately priced Shop benefit.

## 6. Revenue streams and guardrails

| Revenue stream | Who pays | When to introduce | Guardrail |
|---|---|---|---|
| Basic listing | No charge | Pilot | Max active listings per account; spam controls |
| Featured listing | Seller | After organic traffic | Label as sponsored/featured; no ranking deception |
| Shop merchant plan | Business seller | After repeat merchant demand | Separate from existing organisation plan |
| Shop-sponsored campaign | Advertiser/business | Once inventory/reporting exists | New placement contract, caps, consent, and reporting |
| Checkout commission | Seller, initially proposed | After approved checkout | Show net proceeds; handle refunds, disputes, reversals |
| Delivery margin | Buyer/seller only if offered | Not in MVP | Do not promise logistics before a partner and SLA exist |

No revenue forecast should be presented as fact until pilot data exists. Measure actual listings, listing-to-contact rate, buyer response, completed sales self-reported by both parties, repeat sellers, complaint rate, and the cost of moderation/support.

## 7. Marketplace economics and launch gates

### Pilot metrics

Track a small set of decision metrics:
- **Supply:** active listings, new listings/week, listings per category/campus, share with usable photos.
- **Demand:** unique listing viewers, search-to-detail rate, saves, contact requests.
- **Liquidity:** share of active listings receiving at least one genuine inquiry within 7 days; median time to first inquiry.
- **Outcome:** seller-marked sold rate, buyer/seller confirmation rate if available, repeat listing rate.
- **Trust:** reports per 100 active listings, confirmed scams, moderation response time, repeat offender rate.
- **Economics:** cost per active listing, moderation/support time, gross revenue per paid boost, provider payment costs if checkout later exists.

Initial go/no-go targets are hypotheses to agree before pilot launch, not measured Prepza data. A reasonable first decision is whether a focused campus pilot can generate consistent real inquiries and low manageable complaint volume over 4–6 weeks. Avoid optimizing revenue before these signals exist.

## 8. Payments, delivery, and trust: explicit phased boundaries

### MVP boundary

- Prepza hosts and moderates listings.
- Buyer contacts seller and agrees how to pay and meet.
- Prepza does not receive, hold, or promise to protect the purchase money.
- Prepza does not guarantee the item, seller, delivery, or transaction.
- Users can report a listing or seller and receive clear guidance on what Prepza can and cannot resolve.
- Never collect or expose full card details, M-Pesa PINs, OTPs, or passwords.

This is lower complexity, not risk-free. Clear disclaimers do not remove obligations that applicable law imposes on the platform.

### Checkout boundary

Before enabling in-app checkout, decide and document:
- Whether Prepza acts as a marketplace/intermediary, agent, merchant of record, or another role.
- Who legally sells the item and issues the tax invoice.
- Whether seller onboarding/KYC and tax details are required.
- Supported payment methods and settlement paths confirmed by the provider.
- Refund, return, dispute, chargeback/reversal, fraud, and prohibited-item policies.
- When the seller receives proceeds and what happens when an order is disputed.
- Delivery responsibility and proof of handover.
- Whether a proposed held-funds or escrow arrangement requires separate regulatory approval.

Do not build an internal balance, wallet, escrow, or manual payout ledger as a shortcut.

## 9. Data, safety, and moderation requirements

- Require sign-in to list, save, contact, report, or transact.
- Public listing responses must not expose email, phone number, account IDs, private messages, exact home address, or other private profile fields.
- Verify listing ownership on every edit, pause, delete, and mark-sold action.
- Add rate limits and abuse controls to listing creation, image upload, messaging/contact, and reports.
- Use server-side validation and database constraints for prices, status transitions, and seller ownership.
- Use safe image storage with randomized object keys, file-type validation, size limits, access controls, and deletion policy. Reuse `object_storage.py` only after the public/private image-access model is clear.
- Record moderation decisions and state changes in an audit trail.
- Provide report reasons: scam/suspicious payment, prohibited item, counterfeit, misleading description, harassment, duplicate/spam, and other.
- Provide a moderation queue, listing suspension, seller suspension, appeals/contact route, and repeat-abuse controls before broad launch.
- Publish seller terms, buyer guidance, prohibited-items policy, privacy notice updates, and a complaints process.
- Minimize collection of student and identity information; do not sell student lists or share identifiable student behaviour with advertisers.
- Check whether Prepza's data-controller/processor registration and other privacy obligations cover the new processing purpose. Do not assume existing compliance automatically covers a marketplace.

## 10. Kenya-specific legal and operational checks

These are implementation gates for professional review, not legal advice:

1. **Consumer protection and e-commerce:** confirm disclosures, seller identity/contact requirements, pricing, representations, cancellation/returns, complaint handling, and the platform's role under applicable Kenyan law.
2. **Data protection:** update the privacy/data map for listing photos, seller profiles, messages, location area, moderation reports, and marketplace analytics. Check ODPC registration/obligations for Prepza's actual size and processing activities; exemptions are fact-specific.
3. **Tax and invoicing:** confirm how Prepza records its own listing/advertising/commission revenue and what invoice obligations apply to sellers. KRA states that persons engaged in business generally need to onboard to eTIMS, with specific solutions and exceptions depending on circumstances.
4. **Payments:** get written confirmation from Paystack (or another licensed provider) for the intended marketplace flow and settlement arrangement. Do not treat generic split-payment documentation as approval for this account or flow.
5. **Prohibited goods and intellectual property:** establish rules for counterfeit goods, stolen goods, regulated items, copyrighted materials, and unlawful listings.
6. **University policy:** check whether the pilot campus has rules affecting on-campus selling, delivery, posters, or commercial activity.

Useful official starting points:
- [Paystack — split payments](https://paystack.com/docs/payments/split-payments/)
- [Paystack — transfers and availability](https://paystack.com/docs/transfers/)
- [ODPC — FAQs and registration guidance](https://www.odpc.go.ke/faqs/)
- [ODPC registration portal](https://dataportal.odpc.go.ke/)
- [KRA — eTIMS](https://www.kra.go.ke/online-services/etims)
- [KRA — Buyer Initiated Invoicing](https://www.kra.go.ke/business/etims-electronic-tax-invoice-management-system/learn-about-etims/buyer-initiated-invoicing)
- [Kenya Law — Digital Marketplace Regulations (source text)](https://new.kenyalaw.org/akn/ke/act/ln/2020/190/eng%402022-05-27/source)

## 11. Suggested technical design (future work; no code written)

### Conceptual domain objects

These are proposed concepts only; no existing schema is claimed and no migrations should be created until contracts are approved.

- `shop_listing`: seller ID, title, description, category, condition, price in integer KES, negotiable/free flags, campus/area, listing status, moderation status, timestamps.
- `shop_listing_image`: listing ID, object key, ordering, image metadata, moderation/deletion state.
- `shop_saved_listing`: user ID, listing ID, created timestamp; unique per user/listing.
- `shop_contact` or existing-chat link: buyer ID, seller ID, listing ID, conversation/reference, timestamps, abuse status.
- `shop_report`: reporter, target listing/seller, reason, details, state, moderation actor, resolution timestamps.
- Future `shop_order`: buyer, seller, line item snapshot, currency, amount breakdown, payment-provider reference, payment state, fulfilment state, refund/dispute state, timestamps.
- Future append-only payment/settlement event record with provider event ID uniqueness and idempotent processing.

### Invariants

- Listing prices are stored as integer KES, never floating-point values.
- A listing's seller is derived from the authenticated session, not trusted request data.
- Only active, approved, non-expired listings appear in browse/search results.
- Only the owner or authorized moderator can change a listing.
- A paid boost is not considered active until the provider confirms payment server-side.
- If checkout is introduced, a browser redirect alone never proves payment. Verify signed provider events/server-side status and enforce unique idempotency keys.
- Duplicate provider webhooks must not duplicate an order, commission, refund, or seller settlement.
- Order amounts are snapshotted at checkout so later listing edits cannot change a paid order.
- A seller cannot mark another seller's item sold; order/listing status transitions are constrained and audited.
- Listing deletion must follow an agreed retention and dispute-evidence policy rather than blindly deleting records.

### Backend and frontend boundaries

- Add marketplace routes in a focused module rather than expanding the already-large `app.py` further.
- Keep pricing, moderation, and order-state rules server-side.
- Reuse the existing `api()` helper and navigation stack, but add a typed Shop API contract and dedicated components/screens rather than a large inline implementation in `App.tsx`.
- Introduce a dedicated test suite for listing ownership, visibility, price validation, moderation, report authorization, upload limits, saved listings, seller contact, abuse rate limits, and mobile navigation.
- Add database migrations only after the schema and lifecycle transitions are reviewed.
- Extend admin tooling only with an explicit moderation and audit contract.
- Use feature flags or a controlled pilot allowlist so Shop can be disabled without affecting student study flows.

## 12. Rollout plan

### Stage 0 — discovery and policy
- Interview students from one campus: what they buy/sell, common frauds, current channels, willingness to pay, preferred handover, and trust signals.
- Recruit a small set of initial sellers and seed permitted listings with consent.
- Finalize categories, prohibited items, moderation policy, privacy changes, and seller/buyer terms.
- Confirm whether existing chat can safely support listing-linked contact.
- Agree measurable pilot gates and a named moderation owner.

### Stage 1 — listings and contact (MVP)
- Browse/search/filter/detail.
- Seller listing create/edit/pause/mark-sold.
- Image upload and moderation.
- Save/share/report.
- Safe seller contact.
- Admin moderation queue and audit trail.
- No in-app checkout, escrow, wallet, automated payouts, or delivery promises.

### Stage 2 — paid visibility
- Launch free listings first.
- Test one clearly labelled paid boost.
- Record payment confirmation, duration, placement, impressions, clicks, and refunds.
- Validate willingness to pay and net contribution after provider fees and support effort.
- Keep advertising inventory separate from organic rankings and existing B2B campaigns unless a new explicit contract is approved.

### Stage 3 — merchant tools
- Approved merchant storefronts and business seller support.
- Sponsored Shop placements and aggregate reporting.
- Seller plans only after repeat demand and support costs are known.

### Stage 4 — in-app checkout
- Provider and legal approval.
- Order lifecycle, payment verification, idempotency, refunds/disputes, settlement, delivery/hand-over confirmation, and audit support.
- Staging tests and real low-value end-to-end tests before general availability.

## 13. Acceptance criteria before any code implementation

- [ ] Shop is reachable from Explore without changing existing bottom-nav semantics.
- [ ] Mobile and desktop layouts are responsive, keyboard accessible, and consistent with Prepza's existing design system.
- [ ] Empty, loading, offline, error, no-results, and moderation-pending states are designed.
- [ ] Listings are server-authoritative and ownership is enforced for every mutation.
- [ ] Image upload validation, limits, storage access, deletion, and metadata handling are defined.
- [ ] Report, block, moderation, appeal, and prohibited-item workflows are specified.
- [ ] Privacy and tax/payment responsibilities have been reviewed.
- [ ] No payment is represented as successful based only on client state.
- [ ] All paid placement and eventual transaction fees are disclosed before commitment.
- [ ] Existing student subscriptions, B2B plans, sponsored campaigns, Study Hub, Library, Ada, and navigation regression tests remain green.
- [ ] The pilot has metrics, a moderation owner, and a rollback/disable plan.
- [ ] No implementation begins until this proposal is reviewed and the user explicitly authorizes code changes.

## 14. Research basis and limitations

Research checked on 10 October 2026:
- Paystack documents split settlements through subaccounts/split groups and describes marketplace use cases. This establishes that a technical product exists, not that the proposed Prepza account is eligible or that every Kenyan payment method supports the desired flow.
- Paystack documents transfers as available in Kenya, but transfers are not the same as approval to hold buyer funds or run escrow.
- ODPC guidance describes registration duties and exemptions for data controllers/processors; Prepza must assess its actual facts and processing purposes.
- KRA's eTIMS guidance says persons engaged in business generally need to onboard and issue electronic tax invoices, with specific solutions and rules for small businesses and other circumstances.
- Kenya Law's digital-marketplace tax regulations are relevant background, but their applicability and current consolidated legal position should be confirmed with a Kenyan tax professional.

Market-pricing hypotheses in this document (KES 50–100 boosts, a 5% future seller-side transaction fee, and the 4–6 week pilot) are proposed experiments, not claimed competitor benchmarks or validated demand. The public web research found useful official payment, privacy, and tax guidance but did not establish reliable current marketplace fee benchmarks specific to Kenyan campus marketplaces. Conduct direct competitor checks and student/seller interviews before fixing prices.

---

**Decision requested before implementation:** approve the initial positioning (campus classifieds with direct buyer-seller contact, no Prepza-held funds), the Shop placement under Explore, the pilot categories, and the safety/moderation owner. No code has been changed as part of this proposal.
