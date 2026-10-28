# External Provider Verification Runbook

**Last reviewed:** 2026-10-27  
**Current disposition:** NOT_TESTED against live/sandbox providers. The repository has safe mocked boundary tests, but no verified staging credentials or provider-side delivery evidence is recorded here.

This procedure is deliberately separated from normal CI. CI should never send an uncontrolled email, make a real payment, spend an unbounded AI budget, or start a billable GPU job.

## What is already covered

| Provider boundary | Safe automated evidence | What is still unverified |
|---|---|---|
| Paystack | Fake-client request tests; signed/invalid webhook tests; disposable-PostgreSQL retry/entitlement and campaign-funding tests | Real sandbox checkout redirect and provider-delivered webhook on the configured staging endpoint |
| SES | Fake boto3 client verifies sender, recipient, text/HTML bodies and MessageId | Sender verification, service quota/sandbox rules and delivery to a controlled mailbox |
| OpenAI | Fake HTTP client verifies Responses API URL, model, token limit, usage parsing and missing-key failure | A bounded real generation using an explicitly approved low-limit test project |
| R2 | Fake S3-compatible client verifies put/get/head/presign/delete and key prefixes | Real read/write/delete against a dedicated QA bucket or QA prefix |
| Kokoro/audio/GPU | Worker boundary request mock and worker contract CI | Health/heartbeat and a real short inference job on the configured provider; no paid GPU work has been run |

Relevant tests:
- **tests/test_provider_boundary_mocks.py**
- **tests/test_local_qa_real_world.py::test_paystack_webhook_rejects_bad_signature_retries_then_deduplicates_entitlement**
- **tests/test_local_qa_real_world.py::test_b2b_paystack_campaign_checkout_uses_mock_provider_and_separates_campaign_value**
- **scripts/test_browser_b2b_metering.py**

Mocks prove behavior at the application boundary. They do not prove that a real provider account, region, domain, key, callback URL or GPU worker is correctly configured.

## Where to set test environment variables

**Use a staging service, not the production `prepza` service.** In Render, open the dedicated staging web service, then **Environment** → add/update variables → save changes/redeploy. The staging service must use a disposable/staging PostgreSQL database and Redis, a staging `BASE_URL`, Paystack test-mode keys, a controlled SES sender/mailbox, a capped OpenAI test project, and a dedicated R2 QA bucket. Do not temporarily replace production credentials on the live service just to run this test.

If a manually dispatched GitHub Actions workflow is later used for provider calls, store secrets under **GitHub repository → Settings → Environments → `staging-qa` → Environment secrets**, not in source files or logs. A secret being stored there does not itself run a provider test; only an explicitly approved workflow that names that environment should consume it. The current contract workflows use mocks and do not need real provider secrets.

Set only the variables required for the provider being tested:

| Provider | Staging variables | Notes |
|---|---|---|
| Paystack | `PAYSTACK_SECRET_KEY`, `PAYSTACK_PUBLIC_KEY`, `BASE_URL` | Use matching **test-mode** keys; `BASE_URL` must be the HTTPS staging origin. Never put live keys in staging. |
| SES | `AWS_SES_REGION`, `SES_FROM_EMAIL`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | Use a least-privilege IAM identity and a verified sender; send only to the controlled mailbox. |
| OpenAI | `OPENAI_API_KEY` | Separate test project/key, strict practical spend cap, one synthetic request with at most 128 output tokens. Treat project budgets as alerts unless hard enforcement is verified. |
| R2 app helper | `PREPZA_R2_ENDPOINT`, `PREPZA_R2_ACCESS_KEY_ID`, `PREPZA_R2_SECRET_ACCESS_KEY`, `PREPZA_R2_BUCKET` | Prefer a dedicated QA bucket and credentials restricted to that bucket. The app stores Shop images under the logical `shop-listings/` prefix. |
| Audio worker health only | `PREPZA_INTERNAL_BASE_URL`, `KOKORO_WORKER_TOKEN` or `PREPZA_INTERNAL_TOKEN`, plus worker R2 vars | Inspect health/config only. Do not create a GPU instance or queue an inference job without explicit approval. |

For Render, variable names are case-sensitive. After saving a variable, verify that the staging deployment is healthy before exercising it. Do not copy secret values into `.env.example.vps`, documentation, chat messages, screenshots or logs. Keep a redacted record of which variable names are configured and which are missing.

## Safety rules

1. Use a staging deployment and dedicated provider test credentials. Never paste credentials into source files, issues, logs or this runbook.
2. Paystack must use test-mode keys and a test transaction only. Do not open a production checkout or use a real payment method.
3. SES must send only to a controlled recipient mailbox and from a verified test sender. Do not send to student/customer addresses as a test.
4. OpenAI must use a project/key with a strict spend limit and a tiny token ceiling. Do not include real student documents or personal data.
5. R2 must use a dedicated QA bucket or a dedicated, access-restricted test prefix. Do not overwrite/delete production objects.
6. Do not start a live/billable audio/GPU workload without explicit approval. A mocked synthesis request is the default.
7. If the safe configuration is missing or uncertain, stop and leave the provider gate NOT_TESTED. Never silently fall back to production credentials.

## 1. Paystack sandbox checkout and webhook

### Required configuration

Set these in the staging secret manager, not in the repository:
- **PAYSTACK_SECRET_KEY**: test-mode secret only.
- **PAYSTACK_PUBLIC_KEY**: corresponding test-mode public key where the browser checkout needs it.
- **BASE_URL**: the staging origin used to build the callback URL.
- **PAYSTACK_CUSTOMER_FEE_PASSING_ENABLED**: only set to true when the sandbox/account configuration is explicitly intended to test the B2B pass-through route.

The primary application webhook is **/payment/paystack/webhook**; the B2B campaign webhook is **/payment/paystack/b2b-webhook**. Use the actual configured Paystack webhook destination and ensure it points to staging, not production.

### Procedure

1. Verify the configured key is a test key through the secret manager/account settings without printing its value.
2. Start a disposable B2B campaign with a KES 5,000 test budget (or the current configured minimum) and confirm the initialize request uses KES and the frozen campaign amount in minor units.
3. Complete only a test-mode checkout with the provider’s documented test payment flow. Do not use real money.
4. Capture the provider reference, checkout result and redacted webhook event/time. Verify the HMAC-SHA512 signature was accepted by the staging endpoint.
5. Compare the database: one **b2b_payment**, one **b2b_campaign_funding** row, one funding ledger entry, campaign funding status **funded**, and funded amount equal to the frozen campaign amount. Provider fees must not reduce the campaign’s credited prepaid amount.
6. Replay the same signed webhook through the provider’s retry mechanism or approved staging replay tool. Verify it returns success/duplicate and creates no second funding row or ledger entry.
7. Submit a payload with an invalid signature to staging and verify HTTP 401 with no provider verification call and no data mutation.
8. Record the test reference, environment, exact application SHA and results. Do not include keys or full sensitive payloads.

Student-subscription verification is separate: it must confirm a successful/fulfilled student order before granting Plus/Pro entitlement and prove retries do not create another payment or extend the same period twice.

### Shop listing-posting fee (not a product purchase)

Shop uses the same primary Paystack webhook at `/payment/paystack/webhook`; the browser return URL is `/shop/payment/callback`. In staging, create a second listing for the test student and verify it requires exactly **KES 100**. Complete a Paystack **test-mode** checkout only.

Expected state transitions:
1. Every listing, including the seller's first lifetime listing: KES 100 posting fee.
2. Each listing stays a draft/pending-payment and is not publicly visible until the verified KES 100 payment is recorded. There is no first-listing exemption or free-post bypass.
3. Provider verification must match the saved reference, KES amount (10000 minor units) and KES currency before `posting_fee_paid` becomes true.
4. Successful callback/webhook returns the paid listing to draft; publishing then moves it to pending review; an admin approval makes it visible.
5. Replay the same successful callback/webhook. It must not create another fee, grant subscription entitlements, or award a referral commission for a Shop posting fee.
6. Test failed/abandoned verification and stale-checkout retry. A verified failed/abandoned transaction returns the draft to retryable state. A provider-successful amount/currency mismatch instead enters `payment_review`; it must remain unpublished and cannot be retried until an admin records a manual provider reconciliation note.
7. Verify no buyer-order, seller-payout, wallet or escrow record is created: Prepza does not handle the product purchase.

Record the test reference and redacted ledger/listing states only. No live charge is authorized by this runbook.

## 2. SES email delivery

### Required configuration

Use the configured SES region and a verified sender:
- **AWS_SES_REGION** (or the currently supported AWS region variable)
- **SES_FROM_EMAIL** (or the configured fallback sender)
- AWS credentials supplied by the staging secret manager
- A controlled test recipient that is allowed by the SES account’s sandbox status

### Procedure

1. Confirm the sender and recipient are verified/allowed for the SES account and region.
2. Trigger one test verification or password-reset email for the controlled mailbox only.
3. Record the application result/MessageId without recording the OTP or mailbox secrets.
4. Confirm receipt, subject, text/HTML content, sender and expected expiry/attempt policy.
5. Confirm the application rate-limits repeat requests and handles provider errors without marking an unsent email as delivered.
6. Stop after one or two controlled sends. Record account sandbox/quota status and exact app SHA.

A green fake-client test is not SES delivery evidence.

## 3. Controlled OpenAI generation

### Required configuration

Use a test/staging **OPENAI_API_KEY** from a project with a strict spend limit. Never print the key. Do not enable large document uploads or long podcast generation for this check.

### Procedure

1. Run one short, synthetic academic prompt on a configured task/model with an output cap of at most 128 tokens.
2. Verify the expected Responses API request, a non-empty answer, token usage and cost accounting.
3. Confirm the key/model failure path remains closed if the secret is missing or the provider rejects the request.
4. Confirm plan quotas and the application spend guard still apply.
5. Record model, token counts, elapsed time and reported cost only; do not include private prompt content or the key.

Do not use real student work in provider smoke tests.

## 4. R2 object operations

### Required configuration

Use a dedicated QA bucket or restricted prefix with the application-helper variables:
- **PREPZA_R2_ENDPOINT**
- **PREPZA_R2_ACCESS_KEY_ID**
- **PREPZA_R2_SECRET_ACCESS_KEY**
- **PREPZA_R2_BUCKET**

The standalone audio worker uses a separate set of environment names (**R2_ENDPOINT_URL**, **R2_ACCESS_KEY_ID**, **R2_SECRET_ACCESS_KEY**, **R2_BUCKET**). Verify the app and worker paths separately.

### Procedure

1. Generate a unique QA key under a provider-verification prefix.
2. Put a small synthetic text/audio fixture; read it back and compare bytes and content type.
3. Confirm HEAD metadata and a short-lived presigned URL using an authorized QA client.
4. Delete the fixture; confirm a subsequent HEAD/get no longer finds it.
5. Record the key prefix, bucket identity (not credentials), application SHA and results.

Never run this against student documents or production podcast objects.

## 5. Configured audio/GPU provider

Do not run this as routine push CI. First verify the worker/control-plane health and configuration without requesting work. A live inference test requires explicit approval for the expected cost.

If approved:
1. Use a dedicated QA job/account and synthetic input of only a few seconds.
2. Verify the worker claims one job, reports progress, produces non-empty audio, completes within the requested duration tolerance and writes only to the QA storage prefix.
3. Verify the app can read the resulting object and job status.
4. Delete the QA object/job fixture according to the environment’s retention policy.
5. Record provider identity, region/instance, duration, measured cost, object prefix and exact SHA.

No GPU instance should be started merely to make a CI check green.

## Evidence recording template

Create a dated evidence entry for each provider run. Record:
- application commit SHA and staging environment;
- provider and test/sandbox mode;
- test reference or MessageId where relevant (never the secret);
- exact operation performed and expected/actual result;
- relevant HTTP/job/ledger states and timestamps;
- cleanup result;
- whether the test was mocked, sandboxed or live.

Only mark **external_provider_verification** PASS after the required provider boundaries have actual safe external evidence. If any provider is unavailable, keep the gate NOT_TESTED and record the exact blocker. Overall release remains BLOCKED until every required release gate is supported by evidence.
