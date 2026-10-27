# Prepza: Verified System Walkthrough

**Purpose:** explain the product from the student’s first browser request through persistence, AI, payments, realtime messaging, offline behavior, media storage, and release verification.

**Source checkpoint:** 510baa7190986a2866ee7095e3a6198013b20ab1.
**Important distinction:** “implemented” means the repository contains the behavior; “mock-tested” means the external client was replaced with a fake; “runtime-tested” means the named automated journey actually ran; “provider-verified” means a safe live/sandbox service was reached and verified. These labels are not interchangeable.

## 1. The big picture

Prepza is a React/TypeScript progressive web application backed primarily by a Flask application and PostgreSQL. It has separate runtime entry points for Socket.IO and the podcast audio worker. Redis supports realtime distribution and worker queues; object storage and external APIs sit behind integration boundaries.

~~~mermaid
flowchart TB
  Student[Student / advertiser browser - React PWA] -->|HTTPS JSON| Flask[Flask app - app.py and route modules]
  Student -->|Socket.IO| Realtime[realtime_server.py]
  Student -->|offline reads| Local[Service worker + IndexedDB]
  Flask --> PG[(PostgreSQL - source of truth)]
  Realtime --> PG
  Realtime --> Redis[(Redis - realtime distribution)]
  Redis --> ChatWorker[chat_event_worker.py]
  ChatWorker --> Realtime
  Flask --> AI[ai_service.py]
  AI --> OpenAI[OpenAI Responses API]
  Flask --> Paystack[Paystack API + signed webhooks]
  Flask --> SES[Amazon SES]
  Flask --> Storage[object_storage.py]
  Storage --> R2[(Cloudflare R2)]
  Storage -. compatibility fallback .-> Supabase[(Supabase Storage)]
  Flask --> Podcast[podcast_audio.py + kokoro_control.py]
  Podcast --> PG
  PG --> Kokoro[kokoro_worker/worker.py]
  Kokoro --> TTS[Configured Kokoro endpoint]
  Kokoro --> R2
~~~

This is a logical architecture map, not a claim that every provider is currently configured or reachable. The browser may open cached study material while disconnected; payment confirmation, new AI generation, and realtime transport still require connectivity.

### Main responsibilities

| Area | Main implementation | Authoritative state |
|---|---|---|
| PWA UI, navigation and study screens | frontend/src/App.tsx and frontend/src/** | Browser state is a view/cache; server state remains authoritative for protected operations |
| Authentication, HTTP routes and models | app.py and registered modules | PostgreSQL rows plus authenticated Flask session |
| Database schema evolution | alembic/, alembic.ini, docs/DATABASE_MIGRATIONS.md | Alembic revision graph; verify on disposable databases |
| AI provider boundary | ai_service.py and generation modules | AI job/artifact/usage records in PostgreSQL |
| Student checkout/subscriptions | app.py, student_subscription_billing.py | Payment, student_order and subscription/entitlement state |
| B2B campaign funding and delivery | b2b_campaign_payments.py, b2b_campaign_metering.py, discovery_billing.py | Frozen campaign pricing plus append-only campaign ledger |
| Email verification/recovery | auth_otp.py | OTP records and rate limits in PostgreSQL; SES sends the email |
| Realtime messaging | realtime_server.py, chat_event_queue.py, chat_event_worker.py | Persisted messages in PostgreSQL; Socket.IO delivers updates |
| Podcast/audio | podcast_audio.py, kokoro_control.py, kokoro_worker/worker.py | Job state in PostgreSQL; completed audio object in storage |
| Object storage | object_storage.py plus the worker storage client | Object bytes in configured storage; metadata/ownership in PostgreSQL |

## 2. The ordinary request path

1. The browser loads the React application and PWA shell. The frontend API helper uses fetch with browser credentials and JSON headers; non-success HTTP responses become ApiError exceptions.
2. Flask dispatches the URL to the relevant route. Protected routes check the session; mutating endpoints commonly require a session-bound CSRF token. Session-version and account-status checks can invalidate stale or suspended accounts.
3. The route reads or mutates PostgreSQL. Money, entitlement and campaign flows use transactions, row locks, provider verification and idempotency records rather than treating a successful HTTP response as the source of truth.
4. The browser updates the view from the response. Offline-capable study data can be read from IndexedDB when appropriate.
5. A timeout or lost response does not prove the server failed to commit. Retry paths must reuse the same stable operation identifier when the operation is idempotent.

The web application is a substantial Flask monolith. Route modules reduce some domain coupling, but this is not a fully separated set of microservices. The podcast worker and realtime server are separate processes; most API and business logic remains inside Flask and its route modules.

## 3. Data and migration model

PostgreSQL is the source of truth for users, academic context, documents/materials, orders/payments, organisations/campaigns, chat records and operational queues. IndexedDB is a local offline copy, not a replacement for server-side access control or financial records.

- **alembic.ini** configures Alembic.
- **alembic/env.py** and **alembic/versions/** implement migration setup and revisions.
- **schema/local_baseline.sql** is a schema-only baseline snapshot; it is not a database dump containing production records.
- **tools/run_local_qa.py** creates a QA database, applies Alembic migrations, and runs real-world regressions against the disposable database.

For schema changes, add/update an Alembic migration and test both fresh bootstrap and upgrade from a prior revision. Do not assume a legacy runtime schema initializer proves the production migration path is safe. The release workflow applies migrations to its disposable PostgreSQL service before testing.

### Financial source of truth

Student subscriptions and B2B campaign balances are separate ledgers:

- Student purchases are confirmed against Paystack transaction verification and a durable student order. Paid access must not be granted from the browser callback alone.
- B2B advertising uses the campaign’s frozen pricing snapshot and b2b_campaign_ledger. Successful delivery charges are negative signed minor-unit entries; funding entries are positive; reversals offset earlier charges. Campaign balance is funded amount plus signed ledger entries.
- UI counters and analytics summaries do not replace ledger rows when reconciling advertiser invoices.

## 4. Authentication, access and privacy

- Flask sessions identify the authenticated user. Session-version checks invalidate previous sessions after relevant account/session invalidation.
- CSRF protects state-changing browser requests that use session authentication.
- Organisation access is checked server-side; hidden frontend buttons are not access control.
- AI artifacts for offline replay must be ready and accessible to the current student. Offline state is account-scoped.
- B2B event rows contain internal user IDs for fraud controls and distinct-user analytics. Advertiser reports should return aggregates, never student IDs, email addresses or individual student lists.
- Campus reporting snapshots the campus ID in event metadata so a later profile change does not rewrite the event’s attribution. Campus groups with fewer than ten distinct reached accounts are suppressed. This reduces small-cohort exposure but does not guarantee against every inference using outside knowledge.

## 5. AI generation

ai_service.py is the direct provider boundary. It sends requests to the OpenAI Responses API, checks that a key is configured, applies task-selected model/token limits, parses the response and records token usage/cost for applicable generation paths. Plan allowances, per-request ceilings, artifact reuse, generation fingerprints and stale-job recovery live in surrounding modules and app.py.

Important behavior:

- Reusing a ready matching artifact can avoid a new provider call. Reuse does not prove that provider credentials are live.
- Fresh generation is subject to plan limits and a global spend control. Previously created study material can remain usable when new generation is blocked or the student is offline.
- General document-generation work can use an in-process daemon thread; a database job row does not make that thread a durable distributed queue. Stale-job recovery and artifact idempotency therefore matter.
- New generation is not performed offline. The offline layer serves eligible previously created artifacts instead.

**Verification distinction:** tests/test_provider_boundary_mocks.py replaces the HTTP client and confirms request shape, model name, token cap and missing-key behavior. That is mock-tested, not proof of a live OpenAI key, billing status, latency or response quality.

## 6. Payments and entitlements

### Student subscriptions and purchases

The student flow is primarily in app.py, with lifecycle/refund logic in student_subscription_billing.py. Checkout creates a pending payment/order; a signed Paystack webhook is validated using HMAC-SHA512 and the configured secret; the backend verifies the transaction with Paystack; then local payment/order state and subscription dates/allowances are updated. Duplicate webhook delivery must not create a second payment or extend the same entitlement twice.

The disposable QA suite has a webhook test that injects a temporary provider-verification failure, expects the first signed delivery to fail without granting access, then retries and checks the entitlement transition and duplicate replay. That test replaces the provider request; it is not a live Paystack sandbox delivery.

### B2B campaign funding

b2b_campaign_payments.py handles organisation campaign checkout, signed webhooks and refunds. It freezes campaign economics before checkout and verifies the provider transaction before crediting the campaign. Funding is recorded in the campaign funding table and append-only ledger.

Distinguish three verification levels:

1. **Mock contract:** verifies URL/payload, signature rejection, verification retry and entitlement/ledger transitions with fake HTTP responses.
2. **Sandbox verification:** uses dedicated Paystack test credentials and a test-mode transaction; proves the deployed endpoint/configuration, provider signature delivery, checkout redirect and webhook wiring.
3. **Live payment:** a real customer charge, outside routine QA and never to be initiated without explicit approval.

The repository has mock and disposable-database coverage. Live sandbox behavior remains NOT_TESTED until safe test credentials and a staging/sandbox callback endpoint are explicitly available and verified.

## 7. B2B advertising: viewability, accounting and reports

The student-facing sponsored card is implemented in SponsoredOpportunityCard in frontend/src/App.tsx. It requires at least 50% of the card to intersect the viewport continuously for 1.5 seconds while the page is visible. Scrolling it away or hiding the tab clears the timer. If the browser is offline, no impression request is sent; after reconnect, a new visible interval is required. The backend requires a canonical UUID for impression/click submissions.

~~~mermaid
sequenceDiagram
  participant Browser as Student PWA
  participant API as Flask discovery routes
  participant Meter as b2b_campaign_metering.py
  participant DB as PostgreSQL
  Browser->>Browser: Observe >=50% visibility for 1.5s
  Browser->>API: POST impression with stable UUID
  API->>DB: Check consent, audience eligibility and campaign state
  API->>Meter: Check frozen price, funds and frequency cap
  Meter->>DB: Insert event + ledger debit + counter in transaction
  DB-->>Meter: Commit result
  Meter-->>API: Eligible/duplicate + amount + remaining balance
  API-->>Browser: Acknowledge result
  Browser->>API: POST click with stable UUID
  API->>Meter: Validate prior view, budget and click cap
  Meter->>DB: Write at most one billable click debit
~~~

- The backend checks campaign status/funding/date window, placement, currency, prior impression for a click, prepaid balance, pricing snapshot and user frequency caps. Locks serialize concurrent metering; idempotency keys protect repeated requests when the same event ID is reused.
- Raw click events are stored separately from billable clicks. A repeat interaction may appear in raw analytics while the daily billable click cap prevents a second debit.
- JSON/CSV reports distinguish impressions, unique reach, raw clicks, unique clickers, billable clicks, unique billable clickers, billable CTR, raw CTR, unique CTR, unique billable CTR and net spend. Reports support date, campaign and university filters.
- Campus ID is snapshotted in event metadata. Only aggregates are returned; campus rows under ten distinct reached accounts are suppressed.
- The browser-to-ledger test checks the KES 0.35 impression charge, KES 20 click charge, one debit on a lost-response retry, raw-vs-billable click counts and KES 20.35 reconciled spend.

**Remaining integrity caveat:** the 1.5-second intersection observation happens in the browser; the backend cannot independently observe the DOM. A custom client may call the impression endpoint directly with a valid UUID. Server-side consent, budget, pricing, prior-view and frequency checks constrain abuse, but the current implementation is not tamper-proof independent viewability verification. Keep the B2B monetization gate open until the abuse controls and any needed server-issued qualification/token model are reviewed. Fixed monthly sponsorship packages and CPA/conversion billing are not implied by CPM/CPC support.

## 8. Offline and PWA behavior

There are two different offline layers:

1. **Application shell:** frontend/public/sw.js caches shell/static assets to make the installed app load more reliably. API and Socket.IO responses are not generic shell-cache content.
2. **Private offline data:** frontend/src/offline/** stores eligible study materials/artifacts, audio blobs, queued offline chat/mutations and study activity in IndexedDB/local browser storage with account isolation and reconciliation rules.

Examples:

- frontend/src/offline/generatedMaterials.ts resolves saved generated artifacts. A ready private artifact can be replayed offline; fresh generation still requires connectivity.
- frontend/src/offline/studyHubOffline.ts and the Study Hub activity tracker handle saved study content and offline activity reconciliation.
- frontend/src/offline/chatOfflineQueue.ts and the offline mutation queue handle selected actions with idempotency/deduplication and later sync. Offline queues must not replay non-idempotent financial actions under new IDs.
- B2B ads are not an offline queue: no impression is billed while disconnected. Pending click IDs are preserved in session storage and retried after reconnection/navigation using the same UUID; the backend acknowledges duplicate IDs without another ledger debit.

The dedicated browser test runs inside the release browser workflow with disposable PostgreSQL, Redis, the production app image and Chromium. It covers offscreen/offline display, quick scroll, qualifying visible view, lost impression response, lost click response, capped repeat click and report/CSV reconciliation.

## 9. Realtime messaging

realtime_server.py is a separate Socket.IO entrypoint. PostgreSQL remains the persisted source of truth for messages and conversation state; Redis provides cross-process distribution/presence when configured. chat_event_queue.py and chat_event_worker.py handle the stream/worker side when Redis is configured. A prior Redis reconnect regression restarted a real disposable Redis process while the worker was active and checked that the worker stayed alive, delivered the following event and acknowledged the stream entry.

Realtime and E2EE workflows are re-run on source changes. A green contract or reconnect test proves only the exercised paths; it does not mean every network failure, deployment topology or scale level has been tested. The 400-user performance test remains deferred until functional, recovery and release gates are green.

## 10. Email, object storage and audio

| Boundary | Code/configuration | Mock/runtime evidence | Still needs live verification |
|---|---|---|---|
| SES | auth_otp.py; AWS_SES_REGION or AWS region; configured sender (SES_FROM_EMAIL or fallback); AWS credentials in runtime environment | Fake SES client verifies recipient, body and returned MessageId | Sender verification, region/quota/sandbox rules and delivery to a controlled test mailbox |
| R2 app helpers | object_storage.py; PREPZA_R2_ENDPOINT, PREPZA_R2_ACCESS_KEY_ID, PREPZA_R2_SECRET_ACCESS_KEY, PREPZA_R2_BUCKET | Fake S3-compatible client covers put/get/head/presign/delete and logical key prefix | Dedicated test bucket/prefix credentials and real object round trip |
| Podcast worker R2 | kokoro_worker/worker.py; R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET | Worker contract and fake synthesis request | Verify worker credentials/bucket separately; its environment names differ from app helper names |
| Audio/TTS | podcast_audio.py, kokoro_control.py, kokoro_worker/worker.py; configured local Kokoro endpoint | Mocked request and worker validation | Controlled, explicitly approved end-to-end TTS job against the configured service; no GPU workload was started for this QA |

The differing R2 environment variable names between the app helper and standalone worker are a real configuration detail: they must be verified separately. A successful app-storage mock does not prove the worker can authenticate to its bucket.

## 11. Deployment and process topology

The checked-in docker-compose.vps.yml defines PostgreSQL, Redis, the Flask app, realtime process and chat event worker. The app frontend is built through the production Docker build stage. The release CI workflow builds that image, starts disposable PostgreSQL/Redis, runs Alembic migrations, starts the app and then exercises the real browser flow.

Render/VPS deployment is separate from CI correctness. A green Docker build does not prove the live service has redeployed, its secret values are correct, or external providers are working. Do not deploy while required release gates remain open.

## 12. How to interpret the test layers

| Layer | What it proves | What it does not prove |
|---|---|---|
| Source/contract tests | Important code contracts remain present | Full route/database/browser behavior |
| Provider mocks | Request shape, validation and failure contracts against fakes | Real credentials or provider delivery |
| Disposable PostgreSQL QA | Real Flask routes and transactional behavior against isolated schema/data | Production migration safety unless explicitly rehearsed; live provider behavior |
| Browser-to-ledger regression | Real Chromium → Flask → PostgreSQL for the tested view/click/offline/retry/report path | Every browser/device; tamper-proof viewability; live provider availability |
| Live sandbox verification | The specifically exercised provider path works with test credentials | Production configuration unless separately verified |
| Load test | Capacity under the defined workload | Functional correctness outside that workload |

## 13. Current release caveats and next gates

The source now contains retry-safe ad behavior, raw-vs-billable click analytics, explicit CTR definitions, campus-attributed event metadata, campus privacy suppression and aggregate JSON/CSV reports. Treat this as a progressing implementation, not a signed-off advertising product.

1. Finish Release Browser and Cross-System Regression against the exact current source revision. Keep the full disposable PostgreSQL QA, migration, backup/restore, realtime, E2EE, calling and browser evidence tied to exact commit SHAs.
2. Run the B2B checkout/webhook QA test with a mocked provider: bad signature, provider verification, correct funding, and exact duplicate delivery with no second funding or ledger row. This is separate from live Paystack sandbox verification.
3. Perform controlled provider verification only with confirmed safe credentials. Do not contact a production Paystack checkout, send uncontrolled real email, create unbounded OpenAI spend, write to production storage, or start a billable GPU workload.
4. Complete source-grounded documentation and tracker reconciliation. docs/DAY10_TECHNICAL_DOCUMENTATION.md is a dated implementation snapshot from an earlier code checkpoint; use this walkthrough as the current orientation and keep both checkpoint labels clear.
5. Keep b2b_monetization_integrity IN_PROGRESS until latest browser-to-ledger/report behavior and abuse controls are reviewed; keep external_provider_verification NOT_TESTED until controlled provider evidence exists; keep overall release BLOCKED while any required gate is open. The 400-user load test remains DEFERRED.

### Primary entry points

- app.py — Flask app, sessions, registered modules, student payments and protected HTTP behavior.
- frontend/src/App.tsx — main student app shell and sponsored card.
- discovery_billing.py — discovery eligibility, impression/click routes, aggregate advertiser report.
- b2b_campaign_metering.py — atomic delivery checks and ledger writes.
- b2b_campaign_payments.py — B2B Paystack checkout, signature verification, campaign funding and refunds.
- student_subscription_billing.py — subscription lifecycle and refunds.
- ai_service.py — OpenAI boundary.
- auth_otp.py — SES/OTP boundary.
- object_storage.py — app-side R2 helpers.
- realtime_server.py, chat_event_queue.py, chat_event_worker.py — realtime flow.
- podcast_audio.py, kokoro_control.py, kokoro_worker/worker.py — audio jobs and worker.
- frontend/public/sw.js, frontend/src/offline/** — PWA shell/offline implementation.
- scripts/test_browser_b2b_metering.py, tests/test_provider_boundary_mocks.py, tests/test_local_qa_real_world.py, tools/run_local_qa.py — key verification entry points.


### 2026-10-27 verification update

[Release Browser and Cross-System Regression run 40502457332](https://github.com/apexstudying-cmd/prepza/actions/runs/40502457332) completed successfully against runtime commit `e1d9ef42b533c9fb3fb14de2a4a3d66e30714015`. It built the production app image, migrated disposable PostgreSQL, ran mobile/tablet responsive checks, the B2B browser-to-ledger test, full disposable PostgreSQL QA, and online/offline generated-artifact browser journeys. The full suite passed the student Paystack signature/retry/duplicate-entitlement regression and B2B refund replay/distinct-refund idempotency tests. The B2B browser test passed offscreen/offline no-billing, 1.5-second client-side visibility timing, lost-response retry, server-side rapid-click debounce, and aggregate reporting assertions. Responsive screenshots were uploaded; disposable services/volumes were removed.

This result closes the specific tested browser/disposable-PostgreSQL scenarios only. It does not verify live provider credentials/delivery, and it does not make viewability tamper-proof: the backend still does not independently observe viewport visibility or enforce the client-side dwell interval. External-provider verification remains NOT_TESTED; B2B monetization and the overall documentation audit remain open; release remains BLOCKED.
