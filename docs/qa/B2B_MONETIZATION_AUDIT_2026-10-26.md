# B2B monetization audit — 2026-10-26

## Decision

**Billing foundation: partially verified. Full advertiser ad-engine journey: NOT VERIFIED.** Keep the overall Prepza release blocked. This is a source/test audit, not evidence that a live advertiser campaign has run.

## Optimised work to retain

- `b2b_campaign_metering.py` calculates CPM/CPC/push charges from frozen campaign pricing and writes delivery events and ledger debits transactionally.
- Server-side checks cover campaign status, funding, date window, placement, KES currency, available prepaid balance, prior impression before click, and student frequency caps.
- Campaign/user row locks reduce concurrent overspending. Event keys and ledger idempotency keys protect replays **when the same key is reused**.
- `b2b_campaign_payments.py` checks Paystack webhook signatures, verifies transactions with the provider, and guards refund flows.
- `discovery_billing.py` enforces student discovery consent and recent activity. Advertisers receive aggregate campaign analytics rather than a student list.
- Keep the canonical pricing table, frozen pricing snapshots, and prepaid ledger as the source of truth. Do not create a parallel billing path.

## Existing test evidence

`.github/workflows/b2b-contract-validation.yml` compiles the B2B modules and runs `tests/test_b2b_contract.py` and `tests/test_b2b_billing_regression.py`.

Coverage includes price arithmetic/snapshots, invalid placement or billing mode, click-without-impression rejection, same-key replay, frequency-cap/locking source contracts, Paystack signature logic as a source assertion, refund protections, and canonical pricing ownership. `tests/test_local_qa_real_world.py::test_b2b_prepaid_metering_protects_advertiser_balance_and_locks_campaign_pricing` additionally exercises prepaid event billing and repeated-key behavior using disposable PostgreSQL.

The B2B contract workflow passed in the 2026-10-26 run set (run [40329949857](https://github.com/apexstudying-cmd/prepza/actions/runs/40329949857), code commit `69cc6e6a65edc2897ebc5e99dac57f963e8f5d75`). That is valid evidence for the checks executed, **not** proof of every ad-engine requirement or a live provider flow.

## Gaps against the proposed model

1. **Viewability is not verified.** The impression endpoint accepts a POST; it does not prove the ad was at least 50% visible for 1.5 continuous seconds. No frontend `IntersectionObserver`/visibility timer was found in the source search. Treat current events as submitted impressions, not independently verified viewable impressions.
2. **Retry idempotency depends on the caller.** The impression endpoint creates a random key if `event_id` is absent; the click endpoint creates a random key per request. Retrying without reusing a stable event ID can create a different event. Frequency caps reduce abuse but are not transport idempotency.
3. **Raw and unique clicks are not separate metrics.** Current counters/analytics expose delivered clicks; no distinct unique-click metric was found. Do not promise “50 raw clicks / 1 unique click” yet.
4. **The 750 ms debounce rule is not implemented in the searched source.** Client debounce alone would not be sufficient; server-side rate/fraud rules must remain authoritative.
5. **Reporting is incomplete for the proposed sales contract.** The organisation campaign analytics endpoint returns daily impression/click/application counts and campaign data, but no calculated CTR, unique reach/clicks, or CSV/PDF performance-report export was found. Invoice PDFs are not campaign evidence reports.
6. **Campus attribution is not explicit.** Targeting uses university/program/year/semester; no validated `campus_id` event dimension was found. Do not promise KU-campus-only reporting until attribution is implemented.
7. **Conversion attribution is not proven end to end.** The discovery API has an application event, but the reviewed tests do not prove outbound-link attribution, coupon/WhatsApp reconciliation, or duplicate conversion handling.
8. **Some tests are source-text assertions.** These are useful regression guards, but do not prove route authorization, real browser viewability, transaction rollback, concurrent billing, or a complete advertiser journey.

## Recommended product decisions

- Keep prepaid ledger accounting, frozen prices, server-side eligibility, consent checks, organisation roles, and campaign caps.
- Treat Gemini's suggested prices as business hypotheses to validate with pilots, not defaults to change blindly.
- Avoid persistent device fingerprinting. Begin with authenticated account-level deduplication and scoped event IDs, with documented retention.
- Define “raw click,” “unique click,” “viewable impression,” and “verified conversion” in the advertiser contract before invoicing.
- Only bill an impression after viewability, eligibility, event idempotency, frozen pricing, and available prepaid balance pass server-side checks.

## Required before performance-based ads can be called verified

- [ ] Implement at least 50% visibility for 1.5 continuous seconds in the actual student-facing ad component; reset if it falls below threshold or the tab becomes hidden.
- [ ] Require stable event UUID/idempotency keys; test missing/malformed keys and network retries.
- [ ] Store raw click attempts separately from billable/unique click decisions; define unique-click window and server-side abuse/debounce policy.
- [ ] Add disposable-PostgreSQL tests for consent/targeting, cross-organisation access, campaign states, low balance, duplicate provider webhooks, concurrency, reversals, and ledger reconciliation.
- [ ] Add aggregate reports with date/campaign/university filters, reach, raw clicks, unique clicks, CTR with zero-impression handling, spend, and CSV export; verify no student-level data leaks.
- [ ] Add a browser journey: hidden/offscreen ad does not bill; qualifying visible ad bills once; quick scroll resets the timer; retry does not debit twice.
- [ ] Verify Paystack sandbox transaction/webhook/refund flows and any conversion provider safely; no live payment or paid workload without explicit approval.
- [ ] Rerun B2B workflow and broader disposable-PostgreSQL suite on the resulting SHA and record exact run evidence.

## Release interpretation

B2B accounting controls are a promising foundation, not full verification of the proposed ad engine. Keep `b2b_monetization_integrity` open until end-to-end evidence exists. A green contract workflow alone is not sufficient to mark this gate PASS.
