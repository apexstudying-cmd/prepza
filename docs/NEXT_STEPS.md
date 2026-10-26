# Prepza — Persistent Engineering Execution Tracker

Last updated: 2026-10-26
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
- [x] Day 10 initial repository-grounded technical reference (historical snapshot; not the final deep application walkthrough)
- The final deep technical app study and complete source-grounded frontend/backend architecture diagram is separately tracked as an unfinished item in Section 20.
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
- [x] Upgrade a populated prior-Alembic-revision database to current head and verify schema/data invariants in GitHub Actions run [Existing Database Migration Rehearsal](https://github.com/apexstudying-cmd/prepza/actions/runs/40327691259) (passed 2026-10-26); a sanitized production-like historical snapshot is still useful additional confidence, not claimed by this CI fixture
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
- [ ] Deep technical app study + complete source-grounded frontend/backend architecture diagram — intentionally deferred until the remaining functional, browser and recovery gates are green; finish and verify against current `main` before the final freeze.
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

Still blocking release: representative existing-database migration rehearsal, controlled external-provider verification, recovery-specific gaps not covered by the workflow, final clean regression, and the source-grounded architecture/documentation audit. Shared streak remains intentionally NOT_RELEASED. The 400-user load test remains DEFERRED. No deployment or release freeze is authorized by these results.


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
