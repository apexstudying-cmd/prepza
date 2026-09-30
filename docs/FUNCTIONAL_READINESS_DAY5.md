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


## Live database reconciliation finding

A read-only inspection of the connected Supabase/PostgreSQL database was performed on 2026-09-30.

The current `main` ORM still mapped the retired `Unit`/`UnitProgram` tables and several `unit_id` columns, while the live database has no `unit` or `unit_program` tables and no `unit_id` columns on `content_item`, `group`, `library_publication`, or `learning_concept`. Day 5 reconciles those ORM mappings and legacy compatibility responses without changing the live database.

The live database also lacks active columns currently mapped/used by `main`: `ai_job.user_id`, `ai_job.generation_parameters`, `document_content.material_id`, `message_attachment.source_document_content_id`, `payment.organisation_id`, `user.avatar_storage_path`, and `user.read_receipts_enabled`. No production schema change was made; these remain migration blockers before production verification.

The connected Supabase project also reports 73 public tables with RLS disabled. Representative privilege checks did not show SELECT granted to `anon` or `authenticated`, but disabled RLS remains a defense-in-depth gap. The project also has 31 tables with RLS enabled but no policies, so RLS must not be enabled blindly without policy design.
