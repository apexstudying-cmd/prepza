# Day 5 — Functional wiring and real build-path audit

Date: 2026-09-30
Branch: `main`

## Scope

Day 5 moves from individual screen contracts toward repository-wide runtime wiring:
- frontend startup and import mounting;
- offline chat retry identity;
- Flask message idempotency;
- transactional email runtime imports;
- the actual `pnpm run build` entrypoint rather than only invoking Vite directly.

## Repairs in this pass

### Change-email verification runtime import

`app.py` uses `boto3.client("sesv2", ...)` for the authenticated change-email verification link, but the module did not import `boto3`. `boto3` is already declared in `requirements.txt`; the defect was therefore a runtime NameError rather than a dependency gap.

### Offline chat retry idempotency

The offline queue already generated and preserved `client_message_id`, but the Flask message endpoint ignored it. Day 5 wires that identifier into a server-side idempotency table and conflict-safe insert so a lost response/retry returns the original message instead of creating a second message.

### Build-path hardening

The existing Frontend Build workflow invoked `pnpm exec vite build`, which bypassed the package's declared `prebuild` and `build` scripts. Day 5 changes the gate to exercise `pnpm run build` and then checks that the build did not mutate tracked source.

## Safety boundary

No production database was changed.
No Render deployment was performed.
No VPS or GPU infrastructure was provisioned.
No provider plan was upgraded.

CI must pass before this Day 5 pass is considered complete.
