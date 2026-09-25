# Prepza student billing setup

## 1. Paystack plans

Create two monthly plans in the same Paystack environment as the key used by Prepza:

- Plus: KES 499/month
- Pro: KES 999/month
- Invoice limit: 0 (continue until the student cancels)
- Currency: KES

Copy the resulting plan codes into Render environment variables:
- PAYSTACK_PLUS_PLAN_CODE
- PAYSTACK_PRO_PLAN_CODE

Do this separately for Test and Live environments. Test plan codes must never be used with live keys.

## 2. Webhook

Set the Paystack webhook URL to:
https://YOUR-PREPZA-DOMAIN/payment/paystack/webhook

Prepza verifies the X-Paystack-Signature header before processing events.

The billing flow listens for charge.success, subscription.create, subscription.not_renew, subscription.disable, invoice.payment_failed, refund.pending, refund.processing, refund.processed, and refund.failed.

## 3. Important Kenya payment limitation

Paystack recurring subscriptions currently support cards in Kenya. Paystack's M-PESA/mobile-money channel does not support recurring payments.

Therefore:
- recurring Plus/Pro = card checkout
- one-time/add-on payments can use supported one-time channels such as M-PESA
- never promise automatic M-PESA renewal

## 4. Standard refund policy

Current Prepza configuration:
- standard refund window: 24 hours
- zero paid entitlement consumed: 100% refund
- if paid entitlement was consumed: subscription price minus calculated consumed value minus the published service-retention component
- current provisional service-retention component: 20%
- statutory/legal/exception cases are handled separately and are not removed by the standard policy

The 20% retention value is a business-policy default, not a statement of Kenyan law. It must appear in customer-facing refund terms before purchase.

## 5. Cancellation

Cancellation is not a refund.

When a student cancels:
1. Prepza disables Paystack renewal.
2. Current paid access remains active.
3. No new monthly charge should occur.
4. Access ends at the existing subscription expiry.
5. Paystack subscription events keep local lifecycle state synchronized.

## 6. Refund processing

Never mark a payment as refunded just because an admin clicked a button.

Sequence:
1. Student submits a refund request.
2. Prepza calculates and stores the quote from immutable payment + usage data.
3. Admin reviews/executes the request.
4. Prepza calls Paystack's refund API.
5. Local status remains pending/processing until Paystack sends refund.processed.
6. Only then is the payment marked refunded and its order revoked.

## 7. Usage evidence

Paid feature consumption is recorded against the exact subscription payment:
- Ada
- podcast
- summaries
- questions
- mind maps
- flashcards

Backend artifact caching does not make a student's usage disappear. If the student receives an entitlement, the entitlement ledger is what matters for refund eligibility.

## 8. Database

Migration:
migrations/20260921_student_subscription_refunds.sql

The application also has an idempotent startup schema safety net, but the SQL migration should still be retained and applied through the normal Supabase deployment process so the database change is documented and auditable.

## 9. Production-cost warnings

Paystack's current Kenya pricing is:
- 1.5% for M-PESA
- 2.9% for local card transactions
- international card transactions are higher

Paystack also states that transaction processing charges are non-refundable. Prepza therefore absorbs the processing cost when issuing a refund unless the customer-facing pricing/policy legally and commercially allows another disclosed treatment.

Recurring card billing creates a processing cost on every successful monthly charge.

Prepza also continues to incur normal Render, Supabase, AI-provider, storage, email, and other infrastructure costs. A refund does not reverse already-incurred costs.

## 10. Go-live checklist

- [ ] Test Plus checkout with a Paystack test card.
- [ ] Confirm subscription.create reaches the webhook.
- [ ] Confirm the first payment creates a fulfilled subscription order.
- [ ] Confirm Plus access lasts one month.
- [ ] Confirm a recurring charge creates a new Payment + order and extends access exactly one month.
- [ ] Confirm cancellation stops the next renewal but does not immediately remove current access.
- [ ] Confirm invoice.payment_failed does not grant a new paid period.
- [ ] Confirm zero-usage refund quotes 100%.
- [ ] Confirm consumed-usage refund uses the stored ledger.
- [ ] Confirm refund.pending/processing do not mark the payment refunded.
- [ ] Confirm refund.processed revokes the refunded entitlement.
- [ ] Confirm duplicate webhooks do not create duplicate renewal payments.
- [ ] Publish refund/cancellation terms before taking live payments.
- [ ] Have final consumer/refund terms reviewed for Kenyan law before launch.
