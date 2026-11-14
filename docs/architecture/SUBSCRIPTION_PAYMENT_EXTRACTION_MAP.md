# Subscription and payment screen extraction map

**Status:** dependency map and inline characterization contract passed. The five screens have now moved to frontend/src/screens/billing/SubscriptionScreens.tsx; shared types and payment status metadata have neutral owners. The extraction Frontend Build and full Release Browser are queued.
**Current owner:** frontend/src/App.tsx on the consolidated PR #79 branch.
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

The implementation preserves the existing GET plan/status/usage/history requests, CSRF-protected POST /subscription/upgrade payload, redirect_url navigation, duplicate-submit guard, payment pending/failure messaging, and six-second success redirect with cleanup. No provider call was made. The Frontend Build [43584116109](https://github.com/apexstudying-cmd/prepza/actions/runs/43584116109) and Release Browser [43584116201](https://github.com/apexstudying-cmd/prepza/actions/runs/43584116201) were queued when this note was written; do not mark the extraction verified until both complete.
