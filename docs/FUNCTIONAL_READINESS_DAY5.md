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

The existing Frontend Build workflow invoked `pnpm exec vite build`, which bypassed the package's declared `prebuild` and `build` scripts. Day 5 changes the gate to exercise `pnpm run build` and records the actual package build path as the CI build gate. Prepza's current `prebuild` intentionally applies idempotent source transformations, so a clean-tree assertion would be incorrect for this repository architecture.

## Safety boundary

No production database was changed.
No Render deployment was performed.
No VPS or GPU infrastructure was provisioned.
No provider plan was upgraded.

CI must pass before this Day 5 pass is considered complete.


## CI finding and resolution

The first Day 5 CI run reached `pnpm run build` successfully, including the full existing `prebuild` transformation chain, but the additional clean-tree assertion failed because those transformation scripts intentionally rewrite frontend source during the build. This was a false-positive gate, not a TypeScript/Vite/build failure. The clean-tree assertion was removed; the real `pnpm run build` remains the authoritative frontend build step.

This also confirms that the current build architecture should be treated as a transformation pipeline during later deployment-hardening work rather than assuming the build is source-immutable.
