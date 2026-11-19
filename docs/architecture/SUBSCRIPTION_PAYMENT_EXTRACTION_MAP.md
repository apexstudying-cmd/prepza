# Subscription and payment screen extraction map

**Status:** the five student billing screens and student plan/status/upgrade backend routes are extracted; GET /payment-history is in student_payment_history_routes.py. On candidate e094830e323e9993c2b2dbef6844f9105a4b5523, the truncated registration tail in student_subscription_billing.py has been restored and a webhook-dispatch regression added, but that regression is NOT_TESTED because Release Browser 44472584583 failed before full QA. The shared Paystack callback/webhook remain in app.py; no callback extraction is authorized until all event paths are characterized.
**Current owners:** frontend screens in frontend/src/screens/billing/SubscriptionScreens.tsx; plan/status/upgrade HTTP routes in student_subscription_routes.py; payment history in student_payment_history_routes.py; entitlement and recurring/refund lifecycle in student_subscription_billing.py; shared payment verification/callback/webhook in app.py.
**Goal:** move the existing student subscription/payment screens into a feature module without changing plan selection, checkout, provider redirect, return routing, payment-history display, or any billing rule.

## Active route and state ownership

The App route switch currently mounts:

| Route | Current component | Required navigation |
|---|---|---|
| subscription | SubscriptionScreen | payment, payment-history |
| payment | PaymentScreen | subscription |
| payment-success | PaymentSuccessScreen | home, payment-history |
| payment-failure | PaymentFailureScreen | subscription, payment-history |
| payment-history | PaymentHistoryScreen | browser history back |

The selected plan is intentionally lifted into App state because SubscriptionScreen and PaymentScreen are separate route mounts. Keep the selectedPlan state and setSelectedPlan callback in App; pass them to the extracted screens. Keep the callback that parses the Paystack return query string and selects payment-success/payment-failure in AppShell/App routing, not inside a screen.

## Existing API and runtime contracts

- GET /subscription/plans returns the available plans. Keep the backend response authoritative for price and period; client metadata only supplies display badges/colors/features.
- GET /subscription/status loads the current plan, active state and expiry.
- GET /api/usage/me supplies the current plan allowance/usage summary.
- GET /me supplies the CSRF token before checkout.
- POST /subscription/upgrade sends { plan, phone_number? } with X-CSRF-Token and expects redirect_url, order_tracking_id and merchant_reference. The browser navigates to redirect_url using window.location.href.
- GET /payment-history supplies the latest payment details on success/failure screens and the full history list on the history screen.

Preserve the checkout duplicate-submit guard (redirecting), optional phone number trimming, error reset/handling, plan-loading state, the success screen's 6-second home redirect with timer cleanup, and the failure screen's distinct pending-vs-failed messaging. Do not initiate real provider calls in CI or during refactoring.

## Types and shared presentation dependencies

Current local types in App.tsx:

- SubscriptionPlan: id/name/price/period and optional quota/feature fields.
- SubscriptionStatus: plan/is_active/expires_at.
- PaymentHistoryItem: id/payment_type/content_title/plan/amount/status/provider/reference/created_at.

Current display helpers:

- SUBSCRIPTION_PLAN_META and subscriptionFeatures are subscription-screen-only and can move with the screen module or a small billing presentation helper.
- PAYMENT_STATUS_META is currently exported by admin/AdminPlatform.tsx and imported by App.tsx for student PaymentHistoryScreen. Avoid making the new student billing module import an admin screen module. Move this presentation-only map to a neutral lib/paymentStatus.ts and have AdminPlatform re-export/import it if compatibility requires it.

The screens also use shared api/ApiError, N/useTheme, Ic, Pill, EmptyState and ErrorState. Inject App-owned EmptyState/ErrorState components through typed props; import the shared Pill, API, theme and icon modules directly. Do not import App.tsx from the new feature module.

## Source-transform inventory

A repository search for SubscriptionScreen, PaymentScreen, SUBSCRIPTION_PLAN_META and PaymentHistoryScreen currently finds their active implementation in App.tsx; no active prebuild transform was found targeting these component declarations. Confirm this inventory again immediately before extraction and add any discovered transform to the contract suite. Keep the existing prebuild chain intact.

## Test-first extraction plan

1. Added tests/test_subscription_screens_module_contract.py before moving code. It passed against the current inline implementation in Frontend Build run 43583651298 before extraction. It now requires the new module owner and asserts route wiring, selectedPlan lifting, all endpoints, CSRF header and payload, redirect_url navigation, duplicate-submit guard, payment history fields, pending/failure distinction, and six-second redirect cleanup.
2. Billing response types now live in frontend/src/types/billing.ts; PAYMENT_STATUS_META now lives in frontend/src/lib/paymentStatus.ts and AdminPlatform re-exports it for compatibility.
3. The five active screens now live in frontend/src/screens/billing/SubscriptionScreens.tsx. Their component bodies and route IDs were moved; EmptyState/ErrorState are injected and Pill/shared utilities are imported.
4. App route dispatch now imports the five screen components. The Paystack return-query parser and selectedPlan state remain in App.
5. The module contract test is updated and wired into Frontend Build; the extraction build is queued.
6. Run the full Release Browser and cross-system regression on the exact extraction candidate. Treat that as code regression evidence only; real Paystack sandbox verification remains a separate provider gate requiring safe staging credentials and approval.

## Explicit non-goals

- No pricing, Free/Plus/Pro allowance, entitlement, payment, refund, cancellation, webhook, subscription-period or provider behavior changes.
- No live Paystack checkout, test charge, production payment, purchase or paid service during the refactor.
- No change to the existing backend payment contracts or return URL semantics.


## 2026-11-14 — Extraction implemented; verification pending

The five student screens have moved to frontend/src/screens/billing/SubscriptionScreens.tsx. App.tsx still owns selectedPlan, route dispatch and Paystack return-query parsing. SubscriptionPlan, SubscriptionStatus and PaymentHistoryItem now live in frontend/src/types/billing.ts. PAYMENT_STATUS_META moved to frontend/src/lib/paymentStatus.ts; AdminPlatform re-exports it to preserve the existing module export. App injects its existing ErrorState and EmptyState components.

The implementation preserves the existing GET plan/status/usage/history requests, CSRF-protected POST /subscription/upgrade payload, redirect_url navigation, duplicate-submit guard, payment pending/failure messaging, and six-second success redirect with cleanup. No provider call was made. The moved 390-line screen block was compared against its pre-extraction App.tsx source and is byte-for-byte identical after normalizing only the export/prop signatures. The Verified on the exact PR #79 code head `b24d583f054f056161c714a15d558406672acb4d`:
- Frontend Build [43686512095](https://github.com/apexstudying-cmd/prepza/actions/runs/43686512095) PASS.
- Release Browser and Cross-System Regression [43686511971](https://github.com/apexstudying-cmd/prepza/actions/runs/43686511971) PASS.
- PostgreSQL Backup Restore [43686511937](https://github.com/apexstudying-cmd/prepza/actions/runs/43686511937) PASS; both existing-database upgrade and custom-format restore jobs succeeded.
- 17 triggered workflows succeeded; StudyHub Library Flow [43686511919](https://github.com/apexstudying-cmd/prepza/actions/runs/43686511919) was skipped by path condition.

This verifies the extracted screen boundary on the candidate before the subsequent ambassador backend slice. It does not verify real Paystack provider behavior or authorize a payment.


## 2026-11-17 — Backend student subscription routes extracted

The route-only module `student_subscription_routes.py` owns the existing `GET /subscription/plans`, `GET /subscription/status` and `POST /subscription/upgrade` endpoints. `app.py` passes dependencies explicitly through `register_student_subscription_routes` in `route_registry.py` at the original subscription section, preserving its registration position before ambassador routes.

The module does not own plan configuration or subscription lifecycle policy. `ai_economics.get_plans/get_plan` remains the authoritative plan source; `get_user_subscription_status` remains in the app helper layer; `student_orders.py` still owns pending checkout/order persistence; `student_subscription_billing.py` still owns refund, recurring-charge and subscription lifecycle handlers; and the existing Paystack transaction initializer/verification helpers remain in `app.py`.

The exact route/method map, session authentication, limiter rule/key, CSRF decorator, response fields, pending-checkout recovery, payment creation, order snapshot and validation/error behavior are covered by `tests/test_student_subscription_routes_contract.py` and the registry contract. Backend Shared Extension Contract [44035476830](https://github.com/apexstudying-cmd/prepza/actions/runs/44035476830), Frontend Build [44035476389](https://github.com/apexstudying-cmd/prepza/actions/runs/44035476389) and PostgreSQL Backup Restore [44035476520](https://github.com/apexstudying-cmd/prepza/actions/runs/44035476520) pass on code head `f42d447ddde2c5c72100884f83c2358c6e163535`. Release Browser [44035476605](https://github.com/apexstudying-cmd/prepza/actions/runs/44035476605) remains IN_PROGRESS; do not mark this candidate fully cross-system verified until it completes.

No live Paystack checkout/webhook, payment, production data or provider configuration was used.


## 17 November 2026 — exact-head regression completed

PR #79 head `33024391a7f230704cc74ce338905e13159db313` passed Frontend Build [44035945354](https://github.com/apexstudying-cmd/prepza/actions/runs/44035945354), Backend Shared Extension Contract [44035945449](https://github.com/apexstudying-cmd/prepza/actions/runs/44035945449), Release Browser/Cross-System Regression [44035945337](https://github.com/apexstudying-cmd/prepza/actions/runs/44035945337), and PostgreSQL Backup Restore [44035945370](https://github.com/apexstudying-cmd/prepza/actions/runs/44035945370). 17 triggered workflows succeeded; StudyHub Library Flow [44035945281](https://github.com/apexstudying-cmd/prepza/actions/runs/44035945281) was skipped by path condition. Payment history and Paystack callback/webhook remain to characterize. Release remains BLOCKED.

## 18 November 2026 — payment-history route moved

The existing GET /payment-history handler is extracted to student_payment_history_routes.py, registered through route_registry.py at its original position. The endpoint name, GET path, session authentication, user-scoped subscription/add-on filter, descending timestamp order and payload fields remain unchanged; legacy content payments remain excluded. The focused route and registry contracts passed in Backend Shared Extension Contract [44255257558](https://github.com/apexstudying-cmd/prepza/actions/runs/44255257558), 94 tests total. The exact code head 5cd6338a8435233d0480a1b6449a102f4786cdcc also passed Frontend Build [44255257473](https://github.com/apexstudying-cmd/prepza/actions/runs/44255257473), Release Browser [44255257490](https://github.com/apexstudying-cmd/prepza/actions/runs/44255257490) and PostgreSQL Backup Restore [44255257455](https://github.com/apexstudying-cmd/prepza/actions/runs/44255257455). No provider/payment or UI behavior changed.


Next: characterize the shared Paystack callback/webhook signature, authoritative verification, retry and duplicate-delivery idempotency, event dispatch and ambassador-transfer reconciliation before any extraction.

## 19 November 2026 — restore subscription billing registration tail

The current `student_subscription_billing.py` had stopped inside `register_student_subscription_billing` after the no-active-subscription refund-quote response. The function consequently returned `None`, so `app.py` did not receive the `record_usage`, `quote`, `subscription_created`, `recurring_charge`, `refund_webhook` and `subscription_webhook` handler map. The deleted tail also contained the existing refund-request, cancellation and admin-refund route registrations. The original continuation was restored from historical commit `a86b1fc90c1d73b57e345100c13e11250e66d6fa`; current schema ownership and race-safe upsert logic were kept intact.

The new regression in `tests/test_local_qa_real_world.py` protects route registration and dispatch for subscription creation/lifecycle, refund events and recurring-charge fallback. It is **NOT_TESTED** on candidate `e094830e323e9993c2b2dbef6844f9105a4b5523`: Release Browser [44472584583](https://github.com/apexstudying-cmd/prepza/actions/runs/44472584583) failed at the Shop buyer's first in-app chat message (403 CSRF) before the full PostgreSQL QA step. Do not extract the shared callback/webhook until this test executes on an exact passing head.

Ambassador-transfer branch is not yet characterizable: `_apply_paystack_transfer_result`, `initiate_paystack_transfer` and `sync_paystack_transfer_status` are referenced but no definitions were found in the current source tree. Keep transfer initiation out of scope; recover the intended local status/idempotency contract with mocks and no live payout.
