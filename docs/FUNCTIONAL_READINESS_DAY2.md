# Day 2 — Functionality readiness audit

Date: 2026-09-30
Branch: `main`

## Objective

Verify that the existing Prepza frontend and backend are functionally wired before spending money on new infrastructure.

**Infrastructure decision:** VPS migration is paused. The first real deployment test will use the existing Render architecture when its available build capacity resets. No VPS should be provisioned for this launch phase.

## Evidence checked

- Current `main` baseline before this audit: `8e89af698061d1e6028c32a69b2ac6677863a233`.
- The ten latest launch-contract workflows on that commit were successful: Frontend Build, Student Frontend Contract, Student contract validation, Screen Loading Audit, Chat UX Contract, Realtime Runtime Regression, E2EE Security Regression, B2B contract validation, AI economics validation, and Kokoro GPU worker validation.
- The frontend uses relative same-origin API paths in production.
- The Flask app serves the built frontend from `frontend/dist`.
- PWA manifest, service worker, offline package, local PDF.js reader, onboarding, study activity, chat/E2EE, generation, payments, and provider integrations were inspected at source level.
- The repository contains older branch-specific patch files for several admin backend surfaces. Those patches do not apply cleanly to the current `main` source and therefore were **not** blindly applied.

## Results

### GREEN — student core wiring

The current source contains live backend routes for the core student paths, including:

- signup/login/logout/session profile;
- universities/programs;
- Study Hub documents and document reading;
- summary, quiz, flashcards, mind map and podcast generation;
- AI job polling;
- Library discovery/save/report/publish;
- study time, offline baselines and offline synchronization;
- groups and group posts/files/membership;
- notifications and push subscription;
- subscriptions/payment callbacks;
- ambassador flows;
- chats, messages, read state and attachments;
- user search/follow/profile;
- account deletion.

The automated frontend and backend contract suite is also green on the Day 1 baseline.

### FIXED — onboarding was device-global instead of account-specific

`StudentOnboarding.tsx` previously stored:

`prepza_onboarding_v1_done`

That meant if Student A completed the guide on a shared phone and Student B later logged in on the same phone, Student B could inherit Student A's completed state.

It now stores the completion key as:

`prepza_onboarding_v1_done:<user_id>`

The fix was committed directly to `main`.

### RED — admin frontend/backend route drift

The static audit found a significant mismatch between the current admin UI and the backend actually present on `main`.

The current `App.tsx` references admin endpoints including:

- `/admin/users`
- `/admin/analytics`
- `/admin/ai-usage`
- `/admin/ai-jobs`
- `/admin/announcements`
- `/admin/content-reports`
- `/admin/universities`
- `/admin/programs`
- `/admin/groups`
- `/admin/settings`
- `/admin/opportunities`
- `/admin/organisations`
- `/admin/opportunity-promotions`
- `/admin/payments`
- `/admin/payouts`
- `/admin/ambassadors`
- `/admin/auth/otp`
- `/admin/system/capacity`

Many of these are not declared in the current backend route registry.

The repository contains historical patch files that include some of these missing implementations, which confirms that the UI/backend drift is real rather than a simple typo. However, those patches are based on older source contexts and fail a clean hunk application against today's `app.py`. They must be reconciled deliberately rather than pasted over current production logic.

**Impact:** student study functionality is not the same thing as a fully operational Prepza admin portal. Before a real launch, the admin surfaces used for user management, platform settings, moderation, payments, opportunities and operations must be brought back into alignment with the current backend.

**Do not solve this by deleting the admin UI.** Reconcile the existing intended admin behavior with the current backend and preserve current security/CSRF/audit protections.

### YELLOW — production-only behavior still cannot be proven yet

These require the Render deployment rather than more local code speculation:

- real PostgreSQL connection and current production schema;
- real Redis/realtime behavior;
- SES delivery and sender verification;
- Paystack checkout/webhook lifecycle;
- R2 upload/read/delete/presigned URL behavior;
- Render cold-start behavior and actual mobile PWA install/update behavior;
- real AI provider credentials and spend controls;
- Kokoro worker connectivity;
- real offline replay against a deployed API;
- progressive capacity/load measurements.

## Important PWA observation

The service worker is intentionally network-authoritative for navigations and has a 30-second navigation timeout, with cached shell fallback for genuine offline use. This is appropriate for a Render free service that may sleep, but it still needs a real mobile deployment test before launch.

The current source also contains a native-study-page matcher using an escaped `\\d` sequence. It does not currently create a launch blocker because native study pages are deliberately returned from the network rather than cached by the service worker, but it should be cleaned up when the PWA layer is next touched.

## Day 2 decision

**The audit is not marked fully GREEN.**

The correct state is:

- Student core: **GREEN by source/CI contract**
- Frontend build: **GREEN on the Day 1 baseline**
- Realtime/E2EE: **GREEN by regression contracts**
- Offline architecture: **GREEN by regression audit**
- PWA delivery: **GREEN by build/source contract, deployment proof pending**
- Admin portal: **RED — backend reconciliation required**
- Real deployment: **YELLOW — Render verification pending**
- VPS migration: **PAUSED**
- Launch spending: **minimize until the academic environment settles**

## Next work order

1. Reconcile the admin frontend/backend contract on `main`.
2. Add an automated admin route-drift regression check so this cannot silently recur.
3. Re-run the complete CI suite after the reconciliation.
4. Continue non-infrastructure functional audit of the remaining student screens.
5. When Render capacity resets, deploy the exact tested `main` commit.
6. Perform the real mobile smoke test before paying for a VPS or other persistent infrastructure.

No production database migration or VPS provisioning is required for this phase.
