# Prepza — Persistent Engineering Execution Tracker

Last updated: 2026-10-29
Branch: main

Status:
- [x] completed/verified
- [~] in progress/partially verified
- [ ] not yet completed

Rule: require evidence before marking production work complete.

## AI tutor identity and architecture checkpoint (2026-10-29)

- [x] Morio identity: main document-tutor prompt, scoped E2EE prompt, student-facing Home/document/chat labels, and `@Morio` mention updated. Internal Ada-named routes/functions remain compatibility details. Frontend build, identity contract, Chat UX Contract, E2EE security, and full responsive/offline/cross-system browser regression passed on runtime commit `fe8bbbb195d2090c481052172b8af5ec9176e9bc` in [run 40856781684](https://github.com/apexstudying-cmd/prepza/actions/runs/40856781684).
- [x] Added a Morio identity regression contract to `scripts/test_morio_identity_contract.py` and wired it into Student Frontend Contract CI.
- [~] Study retrieval/RAG: extracted per-page text is persisted in `document_page_text`; `study_retrieval_service.py` applies owner or exact university/program/year/semester-approved-publication permissions in SQL before returning passages; the authenticated/CSRF-protected `POST /api/study/retrieval` returns document-version/page citations. Morio's ordinary document tutor now passes the selected server-authorized document into retrieval, sends only the ranked excerpts in a separate prompt block, instructs the model not to guess when evidence is insufficient, and downgrades citations to pages not retrieved. Re-extraction changes invalidate ready generated materials and clear the legacy material pointer. The synthetic 10-query benchmark now measures Recall@5, Precision@5, and MRR@5; access control, citation formatting, no-evidence behavior, and native-only backfill tests are included in AI economics CI. The focused workflow passed 77 tests on [commit 1c810e63](https://github.com/apexstudying-cmd/prepza/actions/runs/40873026717); the full disposable PostgreSQL and online/offline browser journey passed on [commit c3cb4856](https://github.com/apexstudying-cmd/prepza/actions/runs/40872301164), and the same full browser workflow is rerunning with the alert-threshold changes in [run 40873026716](https://github.com/apexstudying-cmd/prepza/actions/runs/40873026716). Remaining: apply both additive SQL migrations through the controlled migration process, dry-run and review `scripts/backfill_document_page_text.py` against existing ready PDFs, evaluate with representative real course material and human-reviewed answer/citation faithfulness, and decide whether/when to enable billable embeddings. E2EE selected-context tutoring remains separate.
- [x] Documented system prompts, MCP tools, access boundaries, guardrails, cache/router behavior, and observability in `docs/DAY10_TECHNICAL_DOCUMENTATION.md`.
- [~] AI/HTTP observability: structured AI events include trace IDs, model/provider, latency, token/cache/cost, prompt/schema versions, and HTTP correlation IDs. Flask middleware generates a server-owned `X-Request-ID`, propagates it into AI logs, stores only 5xx/slow-request metadata, and prunes events after 14 days. Protected `GET /admin/observability` feeds the HTTP observability panel in Admin Operations with recent events and five-minute alert signals. AI economics CI verifies request-ID privacy/correlation and alert thresholds. The focused workflow passed 77 tests on [commit 1c810e63](https://github.com/apexstudying-cmd/prepza/actions/runs/40873026717). Threshold crossings are now emitted automatically as structured warning logs when slow/error events are persisted, rather than only when the dashboard is opened. Remaining: apply the observability SQL migration through the controlled migration process, configure external log/email/pager delivery, verify browser/provider request-ID propagation, and add MCP tool audit logs.
- Guardrail: use mocked embeddings in CI; do not make billable OpenAI embedding calls, live payments, or GPU workloads without explicit approval.

## Local developer tooling checkpoint (2026-10-28)

- [x] Install and verify AWS CLI v2.39.0 in the Windows user-local install location; official script and downloaded MSI signatures verified.
- [x] Configure AWS CLI profile `prepza-dev` with application default region `eu-north-1`; browser login and `sts get-caller-identity` succeeded. Never record identity output or credentials here.
- [x] Configure AWS Agent Toolkit in `us-east-1`; available-skills listing succeeded.
- [x] Record sanitized setup state, agent detection, incomplete Codex MCP setup, safety limits, and follow-up steps in [AWS Agent Toolkit Setup](ops/AWS_AGENT_TOOLKIT_SETUP.md).
- [ ] Inspect and reconcile official AWS starter rules and MCP profile configuration with existing project/agent rules; preserve existing instructions and unrelated MCP entries.
- [ ] Verify read-only AWS MCP access in the actual coding agent before inventory work. The current ChatGPT conversation is not automatically connected to the local MCP server.
- Guardrail: no AWS resource provisioning, purchases, production deployment, billable AI calls, or GPU workloads without explicit approval.



## 1. Repository and audit work
- [x] Day 1 launch audit
- [x] Day 2 functionality-readiness audit
- [x] Day 3 admin route reconciliation
- [x] Day 4 student-screen source audit
- [x] Day 5 runtime dependency/schema reconciliation
- [x] Day 7 auth/session/ownership/offline/realtime/failure audit
- [x] Day 8 runtime/storage/database/migration/jobs/backups/self-hosting audit
- [x] Day 9 freeze/regression and launch-contract CI work
- [x] Day 10 initial repository-grounded technical reference (historical snapshot; not the final deep application walkthrough)
- [x] Final deep technical app study and source-grounded frontend/backend architecture map added at `docs/architecture/VERIFIED_SYSTEM_WALKTHROUGH_2026-10-27.md`; reconcile all QA records against the latest browser evidence before final freeze.
- [x] OpenAI-only provider/dependency cleanup
- [x] Direct-to-main workflow retained
- [x] Re-run full launch-contract CI after latest Alembic/Docker/Study Hub changes — GitHub Actions passed on code commit `6c88a908c5088d23f869d6a564b9ff1c90b8caed`

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
- [x] PostgreSQL backup/restore rehearsal with restored-database application smoke tests passed in GitHub Actions run [8](https://github.com/apexstudying-cmd/prepza/actions/runs/40329949883)

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
- [x] Test a representative future Alembic migration: Shop schema upgrade passed in [Existing Database Migration Rehearsal run 40514771584](https://github.com/apexstudying-cmd/prepza/actions/runs/40514771584); production-like restored snapshot remains a separate optional confidence check
- [x] Upgrade a populated prior-Alembic-revision database to current head and verify schema/data invariants in [PostgreSQL Backup Restore Rehearsal run 40712703724](https://github.com/apexstudying-cmd/prepza/actions/runs/40712703724) (passed 2026-10-28); this includes Shop tables/payment columns and preserved existing document data. A sanitized production-like historical snapshot is still useful additional confidence, not claimed by this CI fixture.
- [ ] Establish production migration checklist
- [ ] Test migration procedure against a disposable restored database
- [ ] Never stamp production/self-hosted DB without independent schema verification

## 4. Production DB/self-hosting
- [ ] Decide self-hosted PostgreSQL topology only after measured requirements justify it
- [ ] Provision production database only after explicit approval
- [ ] Secure database access
- [ ] Configure secrets
- [ ] Back up before schema changes
- [x] Restore backup into disposable PostgreSQL 17 database in GitHub Actions
- [x] Verify restored schema/data and Alembic state
- [x] Run Flask application smoke tests against restored data (`/health`, database-backed `/universities`, SQLAlchemy sentinel read) — [PostgreSQL Backup Restore Rehearsal run 8](https://github.com/apexstudying-cmd/prepza/actions/runs/40329949883), 2026-10-26
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
- [x] Verify real chat worker survives Redis restart and resumes delivery in GitHub Actions [run 3](https://github.com/apexstudying-cmd/prepza/actions/runs/40329059178)
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
- [x] Study Hub — PostgreSQL runtime, multi-document/content/generated-artifact offline journeys and browser replay passed in release browser run [40502457332](https://github.com/apexstudying-cmd/prepza/actions/runs/40502457332) on runtime commit `e1d9ef42b533c9fb3fb14de2a4a3d66e30714015`
- [ ] Document upload/read
- [x] Offline behavior — release browser run [40502457332](https://github.com/apexstudying-cmd/prepza/actions/runs/40502457332) passed online/offline generated-artifact journeys; do not infer every browser/device combination
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
5. [x] Verify the new Study Hub runtime CI workflow — [release browser run 40502457332](https://github.com/apexstudying-cmd/prepza/actions/runs/40502457332) passed
6. [x] Complete browser-to-browser WebRTC media gate
7. [x] Complete browser/offline Study Hub activity lifecycle coverage
8. [x] Complete multi-document/document-byte/generated-artifact offline persistence gate — release browser run [40502457332](https://github.com/apexstudying-cmd/prepza/actions/runs/40502457332) passed
9. [x] Complete storage/data-integrity backup and restore gate — PostgreSQL backup/restore run [40329949883](https://github.com/apexstudying-cmd/prepza/actions/runs/40329949883) passed
10. [x] Browser/offline, B2B browser-to-ledger and recovery/idempotency scenarios passed in run [40502457332](https://github.com/apexstudying-cmd/prepza/actions/runs/40502457332); external provider-side verification remains separate and NOT_TESTED
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
- [~] Repeatable QA registry — structural trace implemented; final cross-document reconciliation and clean full regression remain open.
- [x] E2EE security regression — current runtime commit `e1d9ef42b533c9fb3fb14de2a4a3d66e30714015` passed [E2EE Security Regression](https://github.com/apexstudying-cmd/prepza/actions/runs/40502457061); broader multi-device protocol remains outside launch scope.
- [x] Personal streak — dedicated PostgreSQL regression is recorded PASS in `qa/release_status.json`; broader shared streak remains intentionally NOT_RELEASED.
- [~] Shared Streak — now in launch scope by user request. Backend routes are registered from chat runtime startup and the chat-header control is wired through the frontend build patch. Focused contract CI and frontend/browser regressions are pending; canonical Alembic schema ownership, lifecycle/concurrency tests, and a two-user browser journey remain open.
- [x] Browser/offline Study Hub lifecycle — reload, visibility, inactivity, offline/reconnect and cross-screen activity coverage passed; see `qa/release_status.json`.
- [x] Storage/backup/restore — PostgreSQL backup restore and application smoke test passed in run [40329949883](https://github.com/apexstudying-cmd/prepza/actions/runs/40329949883).
- [~] Cross-system journeys — browser/offline, payment webhook recovery/idempotency, B2B ledger and realtime reconnect evidence are green; external provider-side execution and final consolidated clean regression remain.
- [x] CI — current release browser workflow passed on runtime commit `e1d9ef42b533c9fb3fb14de2a4a3d66e30714015` in run [40502457332](https://github.com/apexstudying-cmd/prepza/actions/runs/40502457332); external-provider gates are separate.
- [ ] Clean full regression — rerun after all remaining gates are green.
- [x] Deep technical app study + source-grounded frontend/backend architecture map — added in `docs/architecture/VERIFIED_SYSTEM_WALKTHROUGH_2026-10-27.md`; final cross-document consistency review remains before freeze.
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


## 29. 2026-10-19 — Offline Library patch-script regression

- Root cause found in the ordered frontend prebuild transformations: `apply_offline_data_foundation.py` wraps the shared `api<T>` request path in `try/catch`, changing the successful `return body as T` indentation from two spaces to four. The following offline queue transformer retains that nesting, while `apply_offline_study_library.py` previously required the exact two-space string. This is a transformation-order/anchor-contract bug, not evidence that the offline feature itself has stopped working.
- [x] Make the Library save-hook insertion recognize the successful return with flexible indentation and preserve the surrounding scope.
- [x] Add focused tests for original and `try/catch`-wrapped helpers, indentation preservation, idempotence, and a clear error when the expected return is absent.
- [x] Add the focused regression test to the Frontend Build workflow.
- [~] Wait for GitHub Actions on commit `5f012fa464407b2b5778f08259a25efab5acde5d`; at documentation time the runs were queued, so the fix is **not yet CI-verified**.
- [ ] Once CI is green, pull main locally and rerun the actual Windows prebuild/build against the user's existing working tree. Preserve all uncommitted local changes; do not reset or overwrite `App.tsx`.
- [ ] Audit the remaining prebuild scripts for exact-text anchors, safe repeatability, and deterministic output; add focused tests for the highest-risk transformations before broad refactoring.
- [ ] Only after frontend build succeeds, rebuild the production-style Docker image and run the offline artifact browser regression. Do not mark the offline artifact gate PASS from a successful TypeScript build alone.


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
- Shared Streak: **IN PROGRESS**. Launch scope was approved on 2026-10-28; route registration, a chat-header UI, and Alembic revision `20261030_shared_study_streak` are on main. Continue with PostgreSQL lifecycle/concurrency tests and a two-user browser journey; do not mark PASS from structural checks alone.
- Browser/offline Study Hub lifecycle: **NOT TESTED**.
- Backup/restore, cross-system journeys and the prior Shop migration rehearsal have passing evidence; the new shared-streak migration rehearsal and final consolidated clean regression remain open.
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


## 24. 2026-10-07 — Admin Study Hub gate execution exposed test-isolation assumptions

The first execution of `scripts/test_browser_admin_study_time.py` produced **4 failed, 1 passed, 1 teardown error**. This is not yet evidence of a production Study Hub/admin regression. Source inspection confirmed that `/admin/operations` intentionally reports aggregate Study Hub seconds across **all non-admin students**, while the first version of the browser gate assumed its three fixture users were the only students in the database.

The observed values (155 vs 45, 43310 vs 43200, 140 vs 30, 220 vs 110) therefore came from comparing a global aggregate with a fixture-local expectation. The 12-hour ceiling is per student, so a global admin total can legitimately exceed 43,200 seconds when multiple students are present.

The teardown error exposed the deliberate non-cascading `UserKey.user_id` FK. The test cleanup was hardened to commit fixture-owned `UserKey` rows before parent-user deletion, rather than changing the production FK contract.

The gate has now been corrected to:
- reset only its fixture StudyTimeLog rows before isolated cases;
- compare global admin totals against a live baseline;
- assert the exact fixture student's admin top-student row;
- verify admin-account study rows do not increase the global student aggregate; and
- perform child E2EE-key cleanup before fixture-user deletion.

**Next action:** rerun the corrected gate on the rebuilt/current app. If it still fails, treat the new result as a real backend/browser regression and trace the actual query/reconciliation path. Do not weaken `/admin/operations` to satisfy the test.


## 2026-10-07 — Current admin Study Hub browser gate blocker

The corrected `scripts/test_browser_admin_study_time.py` has now been rerun from the disposable Docker QA container.

- Result: **1 passed, 4 failed**.
- The four failures all time out at Playwright navigation to `http://app:5000/` with `wait_until="commit"`.
- The preceding `POST /login` succeeds, so the four cases never reach their Study Time assertions.
- The root route is the Flask `/` handler serving the built frontend `index.html`.

**Current action:** isolate the HTTP response for `/` from inside the temporary QA container and explain the navigation timeout before modifying Study Time logic or weakening the browser gate.

The release tracker remains authoritative: `admin_study_time_visibility` is **IN_PROGRESS**. The separate offline content/artifact gate is also still pending after the IndexedDB v4 migration fix and must be rerun independently.


## 25. 2026-10-18 — Mind Map ready-artifact replay diagnosis and deferred deep study

### Current browser evidence
The user ran `python scripts/test_browser_study_hub_offline_content.py -q` on checkout `400a6ce` after rebuilding the app. My Study local document opening and the API fixture contract passed. Existing ready Summary, Flashcards and Practice Questions rendered. Mind Map did not render its existing `Offline branch` payload and remained on the map-depth configuration screen. No canonical material GET for Mind Map was observed, and the test recorded no material-generation POSTs. The generated-artifact browser gate remains **NOT TESTED**, not PASS.

### Source-level root cause identified
The active build runs `tools/apply_generation_ui_build.py`, which wires the screen from `StudyGenerationScreensClean.tsx`. The build then executes `tools/apply_study_generation_polish.py`, whose replacement template overwrites `MindMapGenerationScreen`. The selected-ready-material replay effect existed in the component source but was missing from the replacement template, so the build erased the fix before serving the UI.

The template was updated in commit `ea149abe` to retain the selected ready-material GET/replay effect. A focused contract test was added in commit `ce7a0afd` to execute the transformer in an isolated temporary tree and assert that the replay wiring survives. Neither the new focused test nor the post-fix real-browser gate has yet been executed in the user's rebuilt checkout; no pass is claimed.

### Next action
Sync current `main`, rebuild the app so the prebuild transforms run, execute the focused frontend generation contract tests, then rerun `scripts/test_browser_study_hub_offline_content.py -q`. Do not weaken the browser assertions, call AI generation, or mark the offline artifact gate green until the complete post-fix run passes.

### Documentation deliverable boundary
The checked-in `docs/DAY10_TECHNICAL_DOCUMENTATION.md` remains an initial reference audited against commit `b63df104` dated 2026-10-01. That historical documentation checkbox does **not** close the separately tracked deep technical app study and complete architecture diagram. Keep that deliverable pending until functional/browser/recovery gates pass, then update the walkthrough and diagram against the verified source before final freeze.


## 26. 2026-10-18 — Current GitHub Actions verification blocker

GitHub's Actions API lists **11 workflows** for commit `15cffb59e6834b746a0892aa5fd41869a213ce85`; each reported `conclusion=failure` within about three seconds of creation. The workflow-job API returned `steps=null` and `logs_url=null`, and fetching decoded job logs returned `BlobNotFound`.

This is a real failed CI state, but the available evidence does not show whether the cause is in the repository code or GitHub Actions runner/log availability. Do not classify those failures as a source-code defect without actionable logs; equally, do not leave the CI gate marked PASS.

**Next action:** retrieve useful job logs or rerun the workflows after confirming runner/log availability. In parallel, perform the local focused generation-contract test and post-fix browser gate. The final freeze remains blocked until CI is resolved and all other release-scoped gates have fresh evidence.

## 27. 2026-10-18 — Updated browser evidence: replay passes once, then a card click is intercepted

### Environment and result
The user synchronized `main` at `cf181e4`, ran the focused pytest command from the Windows host, rebuilt and recreated the Docker app, and then ran `python scripts/test_browser_study_hub_offline_content.py -q`. The Docker build passed. The local pytest command did **not** collect tests: importing `app.py` during module collection ran database schema initialization and attempted to resolve the container-only hostname `postgres` from Windows. It failed before assertions ran; this is an environment/import-coupling issue, not a failed assertion.

The contract test now imports Flask's `app` inside only the backend-route test, so the source-only regression can be selected without booting the backend. That import-isolation change is in commit `d4dd452c`; the intended host command is `python -m pytest -q tests/test_frontend_ai_generation_contract.py -k mind_map_replay`. This command is not yet locally verified.

### Browser evidence
- My Study document reopened from IndexedDB without document-detail or reading GETs.
- `GET /documents` exposed all three fixtures and all five ready material types.
- Existing Summary, Flashcards, Practice Questions **and Mind Map** rendered for Offline Economics Notes, confirming the original missing-template replay path now works for at least that document in the rebuilt app.
- Existing Summary, Flashcards and Practice Questions rendered for Offline Statistics Notes.
- The next Mind Map card for Offline Statistics Notes was visible and stable, but Playwright could not click it because a different `<div>` intercepted pointer events. The test stopped before the remaining materials/documents and later offline assertions. Therefore the full generated-artifact browser gate still has not passed.

### Diagnostic and cautious next step
Commit `6355db53` adds an additive DOM hit-test report to the browser test's click-failure message. It records the target and the elements at its center point, including tag, class, bounding rectangle, positioning, `z-index` and `pointer-events`. This is intended to identify the real obstruction rather than use `force=True` or weaken the UI-level test. The new diagnostic has not yet been run.

### Source-of-truth/duplication follow-up
The incident also exposed duplicated authority: the checked-in component contains a version of `MindMapGenerationScreen`, while `tools/apply_study_generation_polish.py` fully replaces it during prebuild. The immediate safe fix updated the active replacement template and added a test that executes it. Track a follow-up to promote the intended polished component into the canonical TypeScript source and reduce the transformer to a narrow, idempotent patch or validator. Do this carefully after the current browser regression is resolved, then rebuild and rerun the relevant gates; do not attempt a large build-system refactor in the same change as the active click blocker.

**Next:** pull current `main`; run the focused source-transform test with `-k mind_map_replay`; rerun the browser gate (the latest changes only alter tests/diagnostics, so the already rebuilt runtime source remains applicable); inspect the new hit-test details and fix the owning overlay/layout or state bug. Do not use forced clicks.

## 28. 2026-10-18 — Podcast selected-artifact identity and offline replay

The latest user run passed the repaired My Study layout and all 12 Summary/Flashcards/Practice Questions/Mind Map replays, including the private/cacheable canonical GET contract and zero generation POSTs. It then failed at podcast readiness. DOM output showed the custom player from `PodcastGenerationScreen` and audio source `/offline-fixture-audio/0`. The active component was requesting `/podcast-audio` without the selected ready material ID; its custom Play button had no accessible name.

The fix is now committed on `main`: selected canonical podcast material is fetched and validated first, all audio status/poll/start/retry/recovery requests preserve its `material_id`, the custom control has a Play/Pause accessible name, the build-time cache patch recognizes query strings, offline replay is not blocked by a failed usage refresh, and job recovery cannot override the selected artifact. Regression tests assert the selected audio ID and offline Blob replay.

### Next verification

1. Pull latest `main`.
2. Run `python -m py_compile scripts/test_browser_study_hub_offline_content.py tests/test_frontend_ai_generation_contract.py`.
3. Run `python -m pytest -q tests/test_frontend_ai_generation_contract.py -k podcast_replay`.
4. Rebuild and recreate `app` with `docker compose -f docker-compose.vps.yml build app` and `docker compose -f docker-compose.vps.yml up -d --force-recreate app`.
5. Run `python scripts/test_browser_study_hub_offline_content.py -q` and require exact podcast material identity, descriptor/audio Blob caching, offline replay, offline reload, and no-generation-POST assertions to pass.

This browser gate remains **IN_PROGRESS**, and release remains **BLOCKED**, until the rebuilt runtime passes. Do not use force-click, bypass the online/offline assertions, or claim PASS from source inspection alone.


## 21. Release gate update — 2026-10-26

Verified code commit: `6c88a908c5088d23f869d6a564b9ff1c90b8caed`.

The following GitHub Actions evidence is green on this exact code commit:

- [Release Browser and Cross-System Regression run 41](https://github.com/apexstudying-cmd/prepza/actions/runs/40324221821): production Docker image build, disposable PostgreSQL/Redis, Alembic migration, mobile/tablet responsive browser checks, full disposable PostgreSQL QA, online/offline and generated-artifact browser journeys, responsive screenshot upload.
- [Frontend Build run 2865](https://github.com/apexstudying-cmd/prepza/actions/runs/40324221443).
- [E2EE Security Regression run 2974](https://github.com/apexstudying-cmd/prepza/actions/runs/40324221387).
- [Realtime Runtime Regression run 2223](https://github.com/apexstudying-cmd/prepza/actions/runs/40324221275).
- [Screen Loading Audit run 2086](https://github.com/apexstudying-cmd/prepza/actions/runs/40324221236), plus Release QA Trace and student/chat/admin/B2B/AI/Kokoro contract checks.

Newly evidenced PASS gates: mobile responsive visual, the cross-system journeys covered by this workflow, Study Hub offline content/generated-artifact browser journey, and release CI workflows. This is CI/browser evidence, not proof of every physical device or every live provider integration.

Still blocking release: rehearse the new shared-streak migration on a populated database, complete controlled external-provider verification, resolve B2B viewability scope, run the final clean regression, and finish the source-grounded documentation audit. Shared streak is now IN_PROGRESS. The 400-user load test remains DEFERRED. No deployment or release freeze is authorized by these results.


## 22. Existing-database migration rehearsal — 2026-10-26

The new [Existing Database Migration Rehearsal](https://github.com/apexstudying-cmd/prepza/actions/runs/40327691259) passed on code commit `4584de061162a5dc010b03847d4d09a7aea81e1c`.

The workflow builds the production app image, creates an isolated PostgreSQL 17 database, migrates it to the documented prior revision `20261005_chat_attach_source_doc`, inserts representative existing document-content and generated-material rows, upgrades to `20261007_doc_material`, and verifies:
- the existing document and generated-material records retain their content;
- old content remains valid with a NULL `material_id`;
- the migration adds the expected nullable `material_id` column and foreign key;
- assigning a valid material link persists successfully;
- the database reaches the expected Alembic head.

The CI fixture is disposable and is removed after the run. It proves the tested Alembic revision-to-revision upgrade path; it is not a claim that a real production snapshot was restored. Live provider verification and remaining recovery/final regression gates remain open.


## 23. Redis worker outage/reconnect rehearsal — 2026-10-26

The [Redis Worker Reconnect Recovery run 3](https://github.com/apexstudying-cmd/prepza/actions/runs/40329059178) passed on code commit `9d041e5c60a2bff2ea6379acae61d51e780afd65`.

The test started the real `chat_event_worker.py`, restarted a disposable Redis 8 container while the worker was active, then verified the worker stayed alive, published a post-restart chat event to the right conversation, and acknowledged the Redis Stream entry.

The first run reproduced a real bug: `_claim_stale_messages()` let a Redis connection-reset error escape, so the process died before reaching the existing retry handler around `XREADGROUP`. The fix catches transient connection/time-out errors in that stale-message reclaim path. The regression passed after the fix. This validates this specific recovery path; provider/webhook idempotency and restore-plus-application-smoke testing remain open.


## B2B advertising monetization verification — 2026-10-26

Audit: `docs/qa/B2B_MONETIZATION_AUDIT_2026-10-26.md`. Existing prepaid ledger, frozen pricing, consent/eligibility checks, frequency caps, keyed-event replay, and payment/refund contract checks are useful controls. B2B contract CI is not full advertiser-engine verification.

- [x] Implement 50%-visible for 1.5 continuous seconds impression qualification in `SponsoredOpportunityCard`, resetting when hidden/offscreen (code commit `b79bd0197c2b4dca786e5d9a22c687837105e625`).
- [ ] Browser-test timer reset and prove the resulting billable event reaches the disposable PostgreSQL ledger exactly once.
- [x] Backend requires a valid stable UUID event ID for impression/click submissions; B2B CI run 40350611960 passed the UUID validation test on code commit df1552801186bdb4f01821afb5d9569fe838238f.
- [ ] Wire the student-facing caller to reuse one UUID across retries and add endpoint/browser tests for network retries and duplicate billing.
- [x] Require UUID event IDs in backend impression/click routes and send stable impression/click IDs from the sponsored card (B2B workflow run `40351270116` passed).
- [ ] Raw click attempts separate from unique/billable clicks; define server-side debounce/abuse policy.
- [ ] Campaign report with CTR, unique reach/clicks, date/university filters, and CSV export without student-level identifiers.
- [ ] Define and verify campus attribution and outbound conversion attribution.
- [ ] Decide whether flat monthly placement fees and CPA/sprint packages are launch scope; current metering supports impression/click/push delivery, not proven CPA billing.
- [ ] End-to-end browser-to-ledger tests; rerun B2B workflow and disposable PostgreSQL regression on the resulting SHA.

The `b2b_monetization_integrity` release gate is IN_PROGRESS. Overall release remains BLOCKED until the evidence supports PASS.

## 2026-10-27 — B2B browser-to-ledger regression
- [x] Browser-to-ledger metering journey: run [40498397254](https://github.com/apexstudying-cmd/prepza/actions/runs/40498397254) passed on code commit `74f0f0380d731223ea791054350e3ba4abbc9fb6`, including the campus raw-click regression, retry without duplicate debit, viewability timer/offscreen behavior, attribution and JSON/CSV reports.
- [~] B2B monetization integrity remains open for independent viewability qualification and server-side abuse/debounce review; do not imply CPA/fixed-placement billing.
- [ ] External-provider verification remains untested until safe provider-side Paystack sandbox, SES, bounded OpenAI, R2 and audio/GPU evidence is recorded. No live payments or paid GPU jobs without explicit approval.
- [ ] Clean full regression after provider/recovery gates; 400-user performance remains deferred and release remains blocked.


## 2026-10-27 — payment recovery follow-up
- [~] Added a disposable-PostgreSQL regression for duplicate `refund.processed` Paystack webhook delivery and hardened the handler to persist processed refund identities. Test commit: `655e01b8f001ac54929d334950327ce2d759c3c9`; implementation: `3e26d22bf9ceaeadbc98e5f82311b6af02691109`.
- [ ] Confirm the current-main CI run passes the duplicate-refund regression and surrounding full disposable-PostgreSQL suite before treating webhook recovery/idempotency as verified.
- [ ] Keep Paystack sandbox, SES, OpenAI, R2 and audio/GPU provider checks separate; no live payment or billable GPU workload without explicit approval.


## 2026-10-27 — follow-up for current recovery and provider gates
- [ ] Verify current-main release browser run for commits containing the duplicate-refund identity fallback and server-side rapid-click debounce browser assertion. Do not mark the recovery or debounce sub-gates PASS until the full disposable-PostgreSQL/browser run finishes green.
- [ ] B2B viewability remains a product/security limitation: browser IntersectionObserver currently supplies the 50% / 1,500 ms signal; the backend does not independently observe viewport visibility. Keep B2B monetization IN_PROGRESS and do not describe viewability as tamper-proof. Decide on server-side challenge/rate/anomaly controls and document remaining client-trust assumptions before selling verified performance placements.
- [ ] External provider verification needs a non-production staging target and test-only credentials configured through the relevant secret manager: Paystack test-mode keys and staging webhook URL; SES verified test sender plus controlled mailbox; OpenAI test project with strict spend limit; dedicated R2 QA bucket/prefix and scoped credentials; audio/GPU worker health configuration. Never paste secret values into chat or repository. No paid GPU inference or live payments without explicit approval.


## 2026-10-27 — browser/recovery gate results
- [x] Recovery/idempotency coverage passed in [Release Browser and Cross-System Regression run 40502457332](https://github.com/apexstudying-cmd/prepza/actions/runs/40502457332) on runtime commit `e1d9ef42b533c9fb3fb14de2a4a3d66e30714015`: invalid Paystack signature, retry after transient verification failure, duplicate student webhook without entitlement extension, duplicate B2B refund replay, distinct same-amount refund events, and replay-safe campaign ledger behavior.
- [x] Server-side B2B rapid-click debounce browser assertion passed in the same run; raw, unique and billable click semantics are separately asserted in the advertiser report.
- [x] Current release-browser workflow passed: responsive phone/tablet checks, B2B browser-to-ledger journey, full disposable PostgreSQL QA, and online/offline generated-artifact browser journeys; screenshots uploaded and disposable services removed.
- [ ] B2B monetization is still IN_PROGRESS: backend does not independently verify the browser's 50%-visible/1,500 ms condition. Decide on stronger anti-abuse controls and document the client-trust limitation before claiming verified viewability.
- [ ] External-provider verification remains NOT_TESTED until test-only Paystack/SES/OpenAI/R2 configuration and safe provider-side evidence are available. Do not paste credentials into chat/repository; no live payments or billable GPU work without explicit approval.
- [ ] Run the final consolidated clean regression and finish the source-grounded documentation audit after external-provider verification is completed or explicitly dispositioned. Keep release BLOCKED and 400-user load test DEFERRED.


## Shop marketplace — implementation in progress (27 October 2026)

- [x] Product direction approved: campus classifieds, direct seller contact only, no buyer checkout or Prepza-held funds.
- [x] Home entry approved: five quick actions; replace Podcasts with Shop, keep Explore and bottom navigation unchanged.
- [~] Every product listing, including the first, costs KES 100 per 30-day period; manual per-item renewal is implemented and must be verified server-side through Paystack. No free-post allowance or automatic recurring charge.
- [~] Frontend and backend are both implemented: browse/search/detail, draft creation, optimized image upload, seller edit/pause/sold/remove, saved listings, WhatsApp/in-app chat, reporting and admin moderation. Verify the full journey and mobile/tablet visuals before marking complete.
- [~] Verify Paystack amount/currency mismatch quarantine, stale checkout retry, and audited admin payment reconciliation; a provider-successful mismatch must never be treated as paid automatically.
- [x] Prove the populated-database upgrade path through `20261029_shop_period_payment` in [PostgreSQL Backup Restore Rehearsal run 40712703724](https://github.com/apexstudying-cmd/prepza/actions/runs/40712703724); existing document data was preserved and Shop tables/payment columns were verified. The new shared-streak revision `20261030_shared_study_streak` extends the target head; its migration rehearsal is pending.
- [ ] Pass the full Shop browser journey against the latest main SHA: first and subsequent listing periods each require KES 100; expired listings are hidden until renewed; legacy zero-fee drafts cannot publish; mocked Paystack success/failure/retry/idempotency, moderation, saved/report flows, ownership denial and direct chat.
- [ ] Configure staging R2 test bucket/prefix and verify upload/read/delete with restricted credentials; do not use production objects for tests.
- [ ] Configure Paystack test-mode checkout/webhook evidence for the posting fee; never test live buyer payments because Shop does not process product purchases.
- [ ] Finish image lifecycle/retention rules, moderation support ownership, and product policy/privacy review.
- [ ] Run mobile/tablet visual checks for Prepza brand consistency (navy/gold palette, typography, card radii, surfaces, spacing, responsive grid and accessible focus states) and add the Shop gate to the release record only with passing evidence.
- [ ] Keep release blocked until the Shop gate is PASS or explicitly scoped out; source presence alone is not certification.

Cost notes: use the existing R2 helper/prefix, resize/re-encode images on upload, cap at six photos per listing and 5 MB per image, avoid a new paid image service, and measure shared account storage/operations before enabling broader listing traffic. Research and pricing assumptions, the direct-contact-only scope, the KES 100 per-item-per-30-day rule, legacy-draft safeguards and unresolved legal/provider checks are documented in `docs/architecture/shop.md`. R2's current published Standard free allowance is account-wide (10 GB-month, 1M Class A, 10M Class B); verify the current provider price page before launch.


Deployment note (27 October 2026): Render's `prepza` service has auto-deploy enabled for `main`. GitHub commits can enter the deployment queue without a manual deploy action; verify the Render deployment list before assuming a commit is only staged. External-provider and launch gates remain authoritative for release readiness.


## Shop UX and caching follow-up (27 October 2026)
- [x] Record the buyer, seller, moderator, renewal, payment-recovery, and cache behavior in [Shop User Flow](qa/SHOP_USER_FLOW.md); mocked-provider coverage and external-provider verification are distinguished explicitly.
- [x] Add researched screen-by-screen UX/UI and low-cost caching standard at `docs/ux/SHOP_UX_UI_STANDARD.md`.
- [~] Harden tab-memory Shop browse snapshots: public fields only (no viewer saved/is_mine flags or payment/moderation details), immediate same-query snapshot display while revalidating, stale warning/fallback on network failure, latest-request protection, and mutation invalidation. The full release browser/cross-system run passed on `3e77f70`, including the regression that prevents superseded browse responses from overwriting the cache. See [Shop contract](https://github.com/apexstudying-cmd/prepza/actions/runs/40704322072) and [full release browser](https://github.com/apexstudying-cmd/prepza/actions/runs/40704322080).
- [~] Invalidate browse snapshots after listing edits, save/unsave, seller status actions, and admin moderation. Focused regression lives in `tests/test_shop_browse_cache_contract.py`; `scripts/test_browser_mobile_responsive.py` now exercises stale (>5 minute) cache fallback after a failed revalidation at phone/tablet viewports. Both are traced in `qa/release_manifest.json`; Shop contract and full browser regression passed on `3e77f70`, but provider-level R2 behavior remains unverified.
- [x] Shop image upload sets `Cache-Control: private, max-age=86400, immutable` through the existing R2 helper, and Shop presigned GET URLs last 24 hours to match that private cache window (previously 15 minutes). Contract coverage checks both settings. Frontend Build, Shop Marketplace Contract, phone/tablet browser coverage and Release Browser/Cross-System Regression passed on integrated code `3bc3b866`; the documentation-only follow-up commit `557daf93` also has green Frontend Build and focused runtime/security/student/admin/B2B/AI/Kokoro contract workflows. See [Shop contract run](https://github.com/apexstudying-cmd/prepza/actions/runs/40701583898), [release browser run](https://github.com/apexstudying-cmd/prepza/actions/runs/40701583921), and [latest Frontend Build](https://github.com/apexstudying-cmd/prepza/actions/runs/40701631502). Actual R2 response headers and browser-cache behavior remain unverified without safe staging credentials. No separate paid cache service was added.
- [ ] Run safe R2 staging upload/read/delete/head and verify actual Cache-Control plus presigned GET behavior; do not use production objects or fabricate provider evidence.

- [~] Monthly per-item Shop fee: KES 100 buys 30 days; renewals are manual (no automatic charge). Migration grants existing paid listings a 30-day transition period; expiry and payment-callback idempotency are implemented. The integrated full-browser regression passed on `3e77f70` and its Shop journey covers expiry, renewal, and duplicate callback behavior. The Shop migration/backup rehearsal passed on `20261029_shop_period_payment` in run 40712703724. A new shared-streak migration now advances Alembic head to `20261030_shared_study_streak`; the updated migration rehearsal must pass before release freeze.
- [x] Verify latest-head populated-database migration and Shop expiry/renewal/replayed-callback journeys: migration/backup restore passed in run 40712703724, and Shop contract plus full browser/cross-system regression passed on code 3e77f70. Real Paystack/R2 provider-side verification remains open.
- [x] Research commercial seller pricing: retain KES 100/30 days for casual sellers initially; commercial shop subscription tiers are hypotheses only and must be validated before implementation. See `docs/architecture/shop.md`.
