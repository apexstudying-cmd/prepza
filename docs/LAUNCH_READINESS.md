# Prepza launch readiness — Day 1 baseline

Date: 2026-09-30
Branch: `main`
Baseline commit audited: `1e3201476f22eb57c9d1fa17dc111c36b09c5b19`

## Day 1 objective

Freeze the launch scope and identify every remaining launch blocker before infrastructure work begins.

**Rule:** no new product features during the launch hardening window unless a test exposes a required fix.

## Current baseline

- GitHub `main`: clean of open PRs and open issues at the time of this audit.
- Latest main CI family observed on `ef60539bb`: passing for frontend, screen loading, chat UX, student contracts, B2B contracts, realtime runtime, AI economics, E2EE security, Kokoro worker validation, and student frontend.
- Existing AI artifact reuse/deduplication, quota accounting, leases/duplicate collapse, and cost tracking are retained.
- Existing realtime command is retained exactly: `gunicorn -k gthread -w 1 --threads 100 realtime_server:app`.
- VPS Docker/PostgreSQL/Redis scaffolding exists, but the Docker image has **not yet been proven by a real build/run**.
- R2 support exists behind provider-neutral storage helpers, but Supabase Storage fallback paths still exist. Full object-storage cutover is not complete.
- SES code is wired, but live SES production/sender/quota verification remains a deployment task.
- Paystack billing code and tests exist, but live production checkout/webhook verification remains a deployment task.
- The repository has many SQL migrations but no single Alembic/automated production migration workflow. A safe ordered migration/backup/restore procedure remains a launch blocker for the VPS cutover.
- Progressive load-test workflow exists and requires a real staging URL plus test credentials/secrets before it can produce capacity evidence.
- Admin operations already expose database, active-user, AI, B2B and provider telemetry; launch work still needs the organic/referral/retention and unit-economics views needed to measure real demand and margin.
- The unused Anthropic Python dependency was removed from `requirements.txt` during Day 1 hardening. Prepza's active AI routing remains OpenAI-first; podcast speech remains Kokoro.
- Day 1 CI rerun after the hardening/documentation commits: all observed main launch-contract workflows passed, including E2EE Security Regression.

## Launch blockers

### P0 — must pass before production cutover

- [ ] VPS secured and reachable only through the intended HTTPS/reverse-proxy path.
- [ ] Fresh VPS PostgreSQL starts successfully.
- [ ] Test database restore succeeds from a known backup.
- [ ] Ordered schema migration procedure is documented and tested on a disposable PostgreSQL database.
- [ ] Prepza Docker image builds successfully from the exact `main` commit.
- [ ] HTTP app starts and `/health` succeeds against PostgreSQL + Redis.
- [ ] Realtime service starts with the existing 1-worker/100-thread command.
- [ ] Redis-backed rate limiting/chat event queue/realtime behavior passes on VPS.
- [ ] R2 upload/read/delete/presigned URL path is tested.
- [ ] SES sender is verified and email verification/password recovery are tested.
- [ ] Paystack live/test environment separation and webhook signature verification are tested.
- [ ] Full CI launch gate passes on the final release commit.
- [ ] Progressive load test passes at the chosen launch capacity with measured CPU/RAM/DB/Redis/error/latency evidence.
- [ ] Backup + restore + rollback procedure is rehearsed.

### P1 — should be completed before broad public launch

- [ ] Admin organic vs referred vs paid acquisition funnel.
- [ ] Retention funnel: signup -> verification -> first study -> second study -> 7-day -> 30-day.
- [ ] Unit economics: revenue/student, AI cost/student, podcast cost/minute, storage cost, gross contribution.
- [ ] Admin alerts/thresholds for database connections, queue depth, AI spend and disk/storage.
- [ ] Launch smoke-test checklist for mobile signup, Study Hub, AI generation, chat, payment and account deletion.

### P2 — can follow controlled launch

- [ ] Full R2 migration of remaining legacy storage paths.
- [ ] More advanced autoscaling/automatic VPS resizing.
- [ ] Additional AI/provider benchmarking.
- [ ] Nonessential UI polish.
- [ ] Additional marketplace/B2B features.

## Day 1 findings

### Engineering

**Status: GREEN for existing CI contracts, YELLOW for production proof.**

The current automated suite is broad and the latest observed main runs passed. That proves the tested contracts, not the complete production environment.

### Infrastructure

**Status: YELLOW.**

The VPS foundation is present. It still needs a real server, real secrets, real PostgreSQL/Redis, HTTPS, backup/restore, and a successful Docker build/run.

### Database

**Status: RED for production migration until procedure is proven.**

The repository contains a sequence of hand-written SQL migrations. We must not guess that the current production database matches them. Before cutover we need:

1. production backup;
2. disposable restore;
3. migration/schema verification;
4. application smoke test;
5. rollback/recovery procedure.

No destructive schema command should be run against production merely to make the app start.

### Storage

**Status: YELLOW.**

R2 support is implemented, but legacy Supabase Storage fallback code remains. We should migrate deliberately rather than deleting the fallback before the VPS/R2 path has been proven.

### Email

**Status: YELLOW.**

SES is wired in application code. Live sender verification, production access, quota and actual email delivery still need to be tested.

### Payments

**Status: YELLOW.**

The Paystack contract is implemented and tested. Live/test keys, plans, webhook URL/signature verification, recurring subscription behavior, cancellation and refund lifecycle still need real-environment verification.

### Capacity

**Status: YELLOW.**

The load-test workflow exists, but no real VPS capacity result has been produced yet. The 4 vCPU / 8 GB target remains a starting hypothesis, not a proven capacity number.

## Remaining launch sequence

1. **Day 1:** scope freeze + launch audit — this document.
2. **Day 2:** VPS provisioning/security + Docker build/run.
3. **Day 3:** PostgreSQL restore/migration procedure + Redis + backups.
4. **Day 4:** R2 + SES + production-like secrets + operational monitoring.
5. **Day 5:** full functional smoke testing.
6. **Days 6–7:** progressive load testing and fixes.
7. **Days 8–9:** security/payment/email/storage final verification.
8. **Days 10–11:** final CI + release candidate + backup/rollback rehearsal.
9. **Days 12–14:** controlled launch to a small student cohort, then expand based on measured results.

## Definition of launch-ready

Prepza is not considered ready merely because the frontend builds.

Launch-ready means:

**code passes + database is recoverable + storage is recoverable + payments are verified + email works + realtime works + AI cost controls work + monitoring works + load test evidence exists + rollback works.**

