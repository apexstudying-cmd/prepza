# Prepza B2B campaign Paystack funding (G2)

## Checkout contract

A sponsored campaign budget is the value credited to the campaign. Paystack processing fees are kept outside that budget.

The launch checkout requires the Prepza Kenya Paystack account to have customer-fee pass-through enabled. Paystack's current documentation says non-Nigerian businesses must contact Paystack support to enable automatic fee pass-through; otherwise the merchant absorbs the fee. Do not enable campaign checkout in production until this has been confirmed.

Render environment:
- `PAYSTACK_SECRET_KEY`: the same secret key used by the live Prepza Paystack account.
- `PAYSTACK_CUSTOMER_FEE_PASSING_ENABLED=true`: set only after Paystack confirms pass-through is enabled for the account.

The application sends the campaign amount to Paystack. Paystack then handles the customer fee separately. The webhook/verification records:
- customer amount actually charged;
- campaign amount requested/credited;
- processing-fee amount;
- provider reference.

## Webhook

Configure the Paystack webhook to:

`https://YOUR-PREPZA-DOMAIN/payment/paystack/b2b-webhook`

The webhook validates the `x-paystack-signature` HMAC-SHA512 signature before processing. It only accepts `charge.success` events whose metadata identifies a sponsored campaign.

The server then verifies the transaction through Paystack before crediting campaign value.

## Funding sequence

1. Organisation owner creates a campaign.
2. Campaign remains draft/pending payment.
3. Owner calls the campaign payment endpoint.
4. Server validates ownership, minimum budget, fee-pass-through configuration, and freezes the pricing snapshot.
5. Server initializes Paystack using the campaign budget in KES minor units.
6. Organisation completes Paystack checkout.
7. Paystack sends signed `charge.success`.
8. Server verifies the transaction and exact requested campaign amount.
9. One database transaction creates campaign funding + append-only funding ledger entry and marks the campaign funded.
10. Payment success never activates the campaign. Approval/activation remains a later server-side lifecycle step.

Duplicate webhook deliveries are idempotent through the provider reference, funding payment uniqueness, and ledger idempotency key.

## Important

The existing Discovery billing module still contains the older usage-invoice path. G2 deliberately does not replace its delivery billing logic; that is part of the later canonical B2B billing/exhaustion work. G3 must make delivery spend use the prepaid campaign ledger atomically.

## Paystack fee note

Current Kenya published Paystack rates are 2.9% for local cards and 1.5% for M-PESA. Paystack's support documentation states that transaction fees can be passed to customers, but automatic dashboard pass-through is currently directly available to Nigerian businesses; businesses in other countries should contact Paystack support. Rates can change, so production economics must follow the live Paystack account terms.
