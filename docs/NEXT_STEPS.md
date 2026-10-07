# Prepza — Persistent Engineering Execution Tracker

Last updated: 2026-10-07
Branch: main

Status:
- [x] completed/verified
- [~] in progress/partially verified
- [ ] not yet completed

Rule: require evidence before marking production work complete.

## 1. Repository and audit work
- [x] Day 1 launch audit
- [x] Day 2 functionality-readiness audit
- [x] Day 3 admin route reconciliation
- [x] Day 4 student-screen source audit
- [x] Day 5 runtime dependency/schema reconciliation
- [x] Day 7 auth/session/ownership/offline/realtime/failure audit
- [x] Day 8 runtime/storage/database/migration/jobs/backups/self-hosting audit
- [x] Day 9 freeze/regression and launch-contract CI work
- [x] Day 10 repository-grounded technical documentation
- [x] OpenAI-only provider/dependency cleanup
- [x] Direct-to-main workflow retained
- [ ] Re-run full launch-contract CI after latest Alembic/Docker/Study Hub changes

## 2. Local Docker/runtime
- [x] Align Docker runtime with Python 3.13
- [x] Build app image
- [x] Build realtime image
- [x] Start PostgreSQL 17
- [x] Start Redis 8
- [x] Verify PostgreSQL health
- [x] Verify Redis health
- [x] Identify stale 15-table local database
- [x] Remove disposable local PostgreSQL/Redis volumes
- [x] Create fresh local database
- [x] Run Alembic upgrade head on empty database
- [x] Verify current Alembic head = 20261005_chat_attach_source_doc
- [x] Verify 108 public tables including Alembic bookkeeping
- [x] Start Flask app
- [x] Start realtime
- [x] Test actual Flask HTTP endpoints through the disposable PostgreSQL QA suite
- [x] Test local realtime authentication/connection
- [x] Test Redis-backed realtime/chat, including worker and cross-process client delivery
- [x] Test representative student flows through the 74-case local QA suite
- [ ] Test representative AI flow with controlled credentials
- [ ] Test local PostgreSQL backup/restore

## 3. Database migrations
- [x] Add Alembic dependency/configuration
- [x] Add Alembic environment
- [x] Add schema-only local baseline
- [x] Fix literal newline corruption in baseline SQL
- [x] Add 20261002_baseline
- [x] Add 20261002_user_model
- [x] Document fresh database migration
- [x] Document existing database verification/stamping rules
- [x] Prove fresh local bootstrap
- [~] Reconcile/document historical migrations versus the current Alembic deployment procedure
- [ ] Test a representative future Alembic migration
- [ ] Establish production migration checklist
- [ ] Test migration procedure against a disposable restored database
- [ ] Never stamp production/self-hosted DB without independent schema verification

## 4. Production DB/self-hosting
- [ ] Decide self-hosted PostgreSQL topology only after measured requirements justify it
- [ ] Provision production database only after explicit approval
- [ ] Secure database access
- [ ] Configure secrets
- [ ] Back up before schema changes
- [ ] Restore backup into disposable database
- [ ] Verify restored schema/data
- [ ] Run application smoke tests against restored data
- [ ] Run migration procedure against production-like database
- [ ] Verify final migration revision
- [ ] Document rollback/recovery
- [ ] Complete real restore rehearsal
- [ ] Establish backup destination/retention/encryption
- [ ] Define RPO and RTO

## 5. Redis/realtime/queues
- [x] Redis Compose service
- [x] Redis health check
- [x] Redis URL wiring
- [x] Socket.IO realtime service
- [x] Redis-backed realtime/chat architecture
- [x] Chat event acknowledgement/recovery
- [x] Single-instance fallback
- [x] Exercise Redis-backed realtime locally
- [ ] Exercise Redis failure/reconnect locally
- [~] Verify queue depth/worker recovery
- [ ] Define production Redis persistence/memory policy
- [ ] Verify production Redis monitoring
- [ ] Verify rate limiting under realistic traffic
- [ ] Verify multi-instance realtime if scaling horizontally

## 6. R2/object storage
- [x] Provider-neutral R2-compatible helper
- [x] Presigned operations in code
- [x] Supabase Storage fallback intentionally retained
- [ ] Configure real R2 test credentials
- [ ] Test upload/read/delete/head
- [ ] Test presigned GET/PUT
- [ ] Test private-object access
- [ ] Test podcast audio upload
- [ ] Establish storage lifecycle/retention
- [ ] Measure storage costs
- [ ] Migrate remaining legacy storage after R2 proof
- [ ] Remove legacy fallback only after evidence

## 7. SES/email
- [x] SES integration
- [x] BASE_URL verification link path
- [ ] Configure test sender/domain
- [ ] Verify sender/domain and credentials
- [ ] Test signup verification
- [ ] Test password recovery
- [ ] Test failure handling
- [ ] Verify production quota
- [ ] Verify monitoring

## 8. Paystack/payments
- [x] Paystack integration
- [x] Subscription/entitlement accounting
- [x] Provider/reference records
- [ ] Verify test/live separation
- [ ] Configure controlled test credentials
- [ ] Test checkout
- [ ] Test webhook signature verification
- [ ] Test entitlement activation
- [ ] Test cancellation/refund/failed payment
- [ ] Verify payment/webhook idempotency
- [ ] Verify live account configuration
- [ ] Document recovery/support procedure

## 9. AI/OpenAI
- [x] OpenAI-only provider boundary
- [x] Current model identifiers represented
- [x] Generation fingerprints
- [x] Exact artifact reuse
- [x] Generation-family collapse/leases/recovery
- [x] Quota/economics accounting
- [x] Per-generation ceilings
- [x] General AI stale-job recovery
- [ ] Verify controlled real OpenAI credentials
- [ ] Test supported generation types against real provider
- [ ] Verify timeout/error/retry handling
- [ ] Measure real token/cost economics
- [ ] Verify monthly allowances
- [ ] Verify artifact reuse does not duplicate provider calls
- [ ] Monitor AI spend and establish alerts

## 10. Kokoro/GPU
- [x] Separate Kokoro control/worker architecture
- [x] PostgreSQL job claiming
- [x] Worker identity/fencing
- [x] Speaker mapping
- [x] Duration correction/verification
- [x] R2 upload path
- [x] GPU autoscaling safety code
- [x] Autoscaler example remains dry-run/manual
- [ ] Test worker locally if feasible
- [ ] Test worker authentication/claim/progress/completion
- [ ] Test failure/recovery
- [ ] Test R2 audio upload
- [ ] Measure CPU performance
- [ ] Measure candidate GPU performance
- [ ] Determine actual launch podcast workload
- [ ] Only then decide whether rented GPU is justified
- [ ] If GPU is used, configure spend/price/worker/credit/idle safety limits

## 11. Security
- [x] Session-version invalidation
- [x] Socket authentication/session checks
- [x] Ownership/privacy checks
- [x] E2EE single-device boundary documented
- [x] Private identity key remains client-side
- [x] Security headers
- [ ] Verify HTTPS/security headers live
- [ ] Verify secrets are not exposed
- [ ] Verify production DB and Redis are not public
- [ ] Review firewall and SSH hardening for self-hosting
- [ ] Review dependency vulnerabilities
- [ ] Design/verify required RLS policies; never enable blindly
- [x] Run authenticated/unauthenticated endpoint checks in local QA/runtime tests
- [~] Test account isolation/logout/deletion; broad FK cleanup audit remains
- [x] Re-run E2EE regression after protocol/storage changes

## 12. Render-first deployment
- [x] Paid VPS migration paused while budget is constrained
- [x] Render-first testing direction established
- [x] Docker runtime proven locally
- [ ] Confirm Render capacity availability
- [ ] Deploy exact tested main commit
- [ ] Verify PostgreSQL/Redis configuration
- [ ] Verify Flask health/realtime/PWA
- [ ] Verify external providers with controlled usage
- [ ] Run functional smoke test
- [ ] Run progressive load test
- [ ] Record CPU/RAM/database/Redis/latency/error evidence
- [ ] Compare measurements with budget
- [ ] Decide whether self-hosting is justified
- [ ] Do not purchase VPS/GPU merely because code supports it

## 13. Self-hosted VPS if justified
- [ ] Select provider/region from measured requirements
- [ ] Provision server
- [ ] Update OS
- [ ] Create non-root user and SSH keys
- [ ] Configure firewall
- [ ] Install Docker and Compose
- [ ] Configure secrets
- [ ] Configure reverse proxy/DNS/HTTPS
- [ ] Start PostgreSQL and Redis
- [ ] Run verified Alembic migration
- [ ] Verify backup/restore
- [ ] Start app/realtime
- [ ] Configure monitoring/backups
- [ ] Run smoke/load tests
- [ ] Rehearse rollback
- [ ] Only then consider public launch

## 14. Monitoring/operations
- [x] Sentry integration
- [x] Admin/provider telemetry
- [ ] Verify live Sentry ingestion
- [ ] Define CPU/RAM/disk alerts
- [ ] Define DB connection alert
- [ ] Define Redis health/memory alert
- [ ] Define AI spend and queue-depth alerts
- [ ] Define error-rate/latency alerts
- [ ] Create operational runbook
- [ ] Test alert delivery

## 15. Capacity/load testing
- [x] Load-test scaffolding exists
- [ ] Obtain real staging/test URL
- [ ] Prepare safe test accounts
- [ ] Define workload profile
- [ ] Run baseline and increasing-concurrency tests
- [ ] Record latency/error/CPU/RAM evidence
- [ ] Record PostgreSQL/Redis behavior
- [ ] Record AI/provider usage separately
- [ ] Identify bottleneck
- [ ] Repeat after optimization
- [ ] Define conservative launch capacity
- [ ] Roll out in controlled cohorts

## 16. Launch smoke test
- [ ] Signup
- [ ] Email verification
- [ ] Login/logout/session invalidation
- [ ] Onboarding persistence
- [~] Study Hub — PostgreSQL runtime and browser/offline activity lifecycle are green; multi-document/content/artifact offline gate is pending
- [ ] Document upload/read
- [~] Offline behavior — Study Hub activity lifecycle is green; real multi-document/document-byte/generated-artifact persistence gate is pending
- [ ] AI summary/flashcards/quiz/mind map
- [ ] Podcast script/audio
- [~] Chat/realtime/E2EE — local distributed realtime + browser WebRTC/media gate green; E2EE identity lifecycle still pending
- [ ] Payment/subscription entitlement
- [ ] Account deletion
- [ ] Admin access
- [ ] In-scope B2B flows
- [ ] Monitoring/error reporting
- [ ] Backup/restore

## 17. Controlled launch
- [ ] Internal test
- [ ] 10–20 students
- [ ] 50–100 students
- [ ] 250–500 students
- [ ] Broader release
- [ ] Monitor errors, CPU/RAM, DB, Redis, AI spend, storage and recovery at every stage

## 18. Future/non-launch work
- [ ] Multi-device E2EE protocol version
- [ ] More advanced infrastructure autoscaling
- [ ] Full legacy storage removal after migration
- [ ] Additional AI/provider benchmarking
- [ ] Nonessential UI polish
- [ ] Additional marketplace/B2B features

## 19. Immediate execution queue
1. [x] Finish local PostgreSQL/Alembic bootstrap
2. [x] Start local app/realtime/Redis/PostgreSQL stack
3. [x] Verify actual local HTTP endpoints through full QA/runtime tests
4. [x] Verify local realtime behavior, including Redis worker and cross-process client delivery
5. [~] Verify the new Study Hub runtime CI workflow
6. [x] Complete browser-to-browser WebRTC media gate
7. [x] Complete browser/offline Study Hub activity lifecycle coverage
8. [ ] Complete multi-document/document-byte/generated-artifact offline persistence gate
9. [ ] Complete storage/data-integrity backup and restore gate
10. [ ] Complete remaining cross-system integration journeys
11. [ ] Run full clean-environment regression/freeze suite
12. [ ] Perform controlled external-provider verification
13. [ ] Run measured staging/load tests after functional/browser gates are green
14. [ ] Decide infrastructure from evidence and budget
15. [ ] Only after freeze, execute Render/VPS deployment work

## 20. Repeatable release QA system
1. qa/release_manifest.json is the feature-trace source of truth.
2. scripts/qa_trace.py verifies declared frontend/backend/database/test/CI links exist.
3. A source trace is not a runtime certification; GREEN requires executed evidence.
4. Every newly released feature must declare its execution path and required runtime tests before it can be called GREEN.
5. actualtest.md records executed evidence; notes.md records engineering reasoning/history; this file records current remaining work.
6. When a gate changes state, update all three records on main rather than relying on chat memory.
7. New gaps discovered during tracing are added here before unrelated work continues.

### Current release-gate queue
- [~] Repeatable QA registry — structural trace implemented; runtime release gate still being expanded.
- [~] E2EE identity lifecycle — source traced; dedicated first-device/reload/restart/second-device/restore tests remain.
- [~] Personal streak — core path exercised through Study Hub; milestone/date-boundary/XP idempotency regression remains.
- [ ] Shared Streak — determine launch scope, registration, canonical schema ownership, frontend wiring, then test if in scope.
- [ ] Browser/offline Study Hub lifecycle — reload, visibility, inactivity, offline/reconnect, cross-screen clock continuity.
- [ ] Storage/backup/restore — backup and actual restore rehearsal.
- [ ] Cross-system journeys — payment→entitlement→usage, upload→processing→artifact, offline→reconcile, realtime failure/reconnect.
- [ ] CI — verify current workflows actually execute and pass on the release commit.
- [ ] Clean full regression — rerun after all remaining gates are green.
- [ ] Final freeze — exact commit, CI, browser, docs, migration and recovery evidence.

## 21. Maintenance rules
1. Evidence before checkbox.
2. Code/scaffolding does not equal production proof.
3. Backup is not complete until restore is tested.
4. Migration is not complete until tested on a disposable database.
5. Never run destructive production DB commands without recovery planning.
6. Historical migrations remain historical unless architecture is deliberately changed.
7. New schema changes should use the current Alembic process unless explicitly documented otherwise.
8. Never enable GPU autoscaling merely because code exists.
9. Never purchase a VPS merely because configuration exists.
10. Prefer measured capacity over guesses.
11. Keep launch scope frozen unless testing exposes a launch-required defect.
12. Update this file on main whenever a tracked item materially changes.
13. Add newly discovered future work here before unrelated work.
14. Record abandoned work rather than silently deleting it.
15. Verified repository/runtime evidence outranks old assumptions.

## Definition of launch-ready

code passes + database is recoverable + storage is recoverable + payments are verified + email works + realtime works + AI cost controls work + monitoring works + load-test evidence exists + rollback/recovery works.

Current status: not yet launch-ready. Local runtime/bootstrap is substantially proven; production infrastructure and external-provider evidence remain outstanding.


## 22. Persistent release-gate status — 2026-10-07

The machine-readable release source of truth is now **`qa/release_status.json`**. It records the latest verified commit, every tracked release gate, its status, evidence, blockers, and next actions.

Current release state: **BLOCKED**.

New evidence reconciled into the tracker:
- Browser-to-browser WebRTC/media gate: **PASS**.
- Study Hub PostgreSQL runtime gate: **PASS (6/6)**.
- Production-style Docker app/frontend build: **PASS**.
- Full disposable PostgreSQL/Alembic QA: **PASS (74/74)**.
- E2EE identity lifecycle: **IN PROGRESS**.
- Personal streak deep regression: **IN PROGRESS**.
- Shared Streak: **IN PROGRESS / scope and wiring decision required**.
- Browser/offline Study Hub lifecycle: **NOT TESTED**.
- Backup/restore, cross-system journeys, CI verification, existing-DB migration rehearsal and final clean regression: **NOT TESTED**.
- 400-user performance: **DEFERRED** until functional/browser/recovery gates are green.

Do not infer completion from an old checkbox or historical note. `qa/release_status.json` and the latest evidence entries in `actualtest.md` are authoritative for current state.


## 23. 2026-10-07 — Next browser gate: real offline content and artifacts

The Study Hub activity/offline lifecycle gate is now green. The next browser gate is deliberately stronger: `scripts/test_browser_study_hub_offline_content.py`.

Run it only after syncing `main` and rebuilding the Docker app so the frontend fixes are actually served.

Required evidence before marking this gate PASS:
- multiple real document Blobs open offline;
- all saved documents survive offline reload;
- summary, flashcards, quiz and mind map open from cached ready artifacts across multiple documents;
- podcast metadata and binary audio resolve locally;
- no generation POST is attempted while offline;
- application offline storage limits remain intact.

Do not call the overall offline feature frozen until this gate passes.


### 2026-10-07 — Offline content gate found a real IndexedDB migration defect

The first execution of the real offline content/artifact browser gate exposed a genuine shared IndexedDB schema issue before its document assertions ran: `prepza-offline-v2` could exist at version 3 with only `savedStudyHub`, while generated-material replay expected `generatedMaterials` and `generatedAudio`. This was fixed on `main` with a version-4 migration that creates all three stores regardless of which offline module opens the database first, including upgrading existing v3 databases.

The next action is therefore unchanged but more important: rebuild the app and rerun `scripts/test_browser_study_hub_offline_content.py`. Do not mark the gate PASS until the full multi-document/artifact/offline-reload/no-generation-POST assertions pass.
