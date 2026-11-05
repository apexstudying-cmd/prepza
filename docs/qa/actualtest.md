# Prepza — Actual QA Test Record

## Post-merge verification — 2026-10-31 (Social follow screen extraction)

[PR #64](https://github.com/apexstudying-cmd/prepza/pull/64) was squash-merged to `main` as `7b0e9301543beabc5dee02af2388983737bada5c`. Its application-code commit `b51e7c4623423bee92234ea4ff9a2dc3482e35b2` moves the existing `FollowListScreen` (followers/following modes) and `FollowRequestsScreen` into `frontend/src/screens/social/FollowScreens.tsx`. The shared `FollowListUser`, `FollowRequestItem`, and `MessageRequestItem` declarations move to `frontend/src/types/social.ts`; the Chats screen imports the same request type contracts.

- Direct comparison against the original `main` source confirms both screen component bodies are unchanged. Only module signatures, narrower navigation callback types, named exports, and the injected existing app-shell `EmptyState` prop differ.
- Route IDs `followers`, `following`, and `follow-requests` remain in `App.tsx`; route composition passes the same active profile IDs and callbacks.
- Existing API endpoint strings, HTTP methods, CSRF header, follow/unfollow state transitions, pending-request handling, request accept/decline behavior, loading/error states, navigation targets, and screen markup remain unchanged.
- The focused social module contract test was written before implementation; its structural assertions failed against the pre-extraction source as expected. The final test suite passed.
- No backend, database, authorization, product-rule, or persistence behavior was changed.

**Post-merge Frontend Build:** [run 41238821182](https://github.com/apexstudying-cmd/prepza/actions/runs/41238821182) passed on exact merge commit `7b0e9301543beabc5dee02af2388983737bada5c`.
- 35 frontend source-transform/module contract tests passed.
- 5 offline Library patch regression tests passed.
- TypeScript typecheck passed.
- Service-worker JavaScript validation passed.
- Vite production build and launch/architecture audits passed.

**Post-merge Release Browser and Cross-System Regression:** [run 41238821241](https://github.com/apexstudying-cmd/prepza/actions/runs/41238821241) passed on the same exact merge commit.
- Production app image built; disposable PostgreSQL and Redis started.
- Alembic migrations and controlled SQL migration ledger passed.
- Mobile and tablet responsive browser checks passed.
- B2B browser-to-ledger metering regression passed.
- Full disposable PostgreSQL QA suite: **98 passed, 0 failed** (3,536 warnings).
- Online/offline and generated-artifact browser journeys passed.
- Responsive screenshots uploaded and disposable services stopped.

Other same-commit workflows passed: Admin Route Contract, Student Contract, Student Frontend Contract, AI Economics, AI Generation Architecture, B2B Contract, E2EE Security, E2EE Chat, Chat UX Contract, Realtime Runtime Regression, Screen Loading Audit, Release QA Trace, Personal Streak Runtime Regression, Shop Marketplace Contract, and Kokoro GPU worker validation. StudyHub Library Flow was skipped by its workflow conditions; no claim is made that this separate workflow ran.

These tests do not certify live Paystack, SES, OpenAI, R2, or GPU provider behavior, and do not clear unrelated product release gates.


## Pull-request verification — 2026-11-05 (Login screen extraction, PR #65)

[PR #65](https://github.com/apexstudying-cmd/prepza/pull/65) extracts the existing Login screen from `frontend/src/App.tsx` into `frontend/src/screens/auth/LoginScreen.tsx`. The PR's source comparison reports the existing 86-line component body as byte-for-byte unchanged after normalizing only the default-export declaration and narrowing the `setScreen` callback type to the three destinations the screen already uses. Existing sign-in and resend-verification API calls, request payloads, Google OAuth navigation, local state, error handling, UI markup, and route destinations are retained.

- **Frontend Build:** [run 41241016697](https://github.com/apexstudying-cmd/prepza/actions/runs/41241016697) passed. Steps include source-transform/module contract tests, offline Library regression, functional wiring and ORM/schema drift audits, TypeScript typecheck, service-worker validation, and the production build.
- **Student Frontend Contract:** [run 41241016700](https://github.com/apexstudying-cmd/prepza/actions/runs/41241016700) passed. Chat UI, Morio identity, StudyHub offline storage, and student screen end-to-end contracts passed.
- **Release Browser/Cross-System Regression:** [run 41241016614](https://github.com/apexstudying-cmd/prepza/actions/runs/41241016614) passed. The job built the production image, started disposable PostgreSQL/Redis, applied Alembic migrations and the controlled SQL migration ledger, ran mobile/tablet responsive browser checks, B2B browser-to-ledger metering regression, the full disposable PostgreSQL QA suite, and online/offline generated-artifact browser journeys.
- The PR description reports E2EE Security, Student Contract, Admin Route, B2B Contract, AI Economics, AI Generation Architecture, Study Navigation, and Prepza Control API workflows passed. StudyHub Library Flow was skipped by its workflow conditions and is not represented as a pass here.

**Scope limitation:** These checks provide evidence for the tested PR paths; they do not establish that every Prepza screen is fully covered, that the whole architecture refactor is complete, or that live Paystack, SES, OpenAI, R2, or GPU providers have been verified. PR #65 was still marked draft at the time of this record; no merge is claimed.

## Post-merge record — 2026-11-05 (Login screen extraction, PR #65)

PR #65 was marked ready after review and squash-merged to `main` as `222b4011c40ddadaae3bdcf331022b79a78f5926`. The documentation-complete PR head was `99583ad6ca22031031a86e069764d71609aed0dd`.

- [Frontend Build run 42000088490](https://github.com/apexstudying-cmd/prepza/actions/runs/42000088490): passed.
- [Student Frontend Contract run 42000088582](https://github.com/apexstudying-cmd/prepza/actions/runs/42000088582): passed.
- [E2EE Security Regression run 42000088501](https://github.com/apexstudying-cmd/prepza/actions/runs/42000088501), [E2EE Chat Validation run 42000088459](https://github.com/apexstudying-cmd/prepza/actions/runs/42000088459), [Admin Route Contract run 42000088625](https://github.com/apexstudying-cmd/prepza/actions/runs/42000088625), [Prepza Control API run 42000088465](https://github.com/apexstudying-cmd/prepza/actions/runs/42000088465), [B2B Contract run 42000088552](https://github.com/apexstudying-cmd/prepza/actions/runs/42000088552), [Student Contract run 42000088628](https://github.com/apexstudying-cmd/prepza/actions/runs/42000088628), [Study Navigation run 42000088583](https://github.com/apexstudying-cmd/prepza/actions/runs/42000088583), [AI Economics run 42000088554](https://github.com/apexstudying-cmd/prepza/actions/runs/42000088554), and [AI Generation Architecture run 42000088598](https://github.com/apexstudying-cmd/prepza/actions/runs/42000088598): passed.
- [Release Browser/Cross-System Regression run 42000088464](https://github.com/apexstudying-cmd/prepza/actions/runs/42000088464): passed production image build, disposable PostgreSQL/Redis, Alembic migrations, controlled SQL migration ledger, mobile/tablet responsive browser checks, B2B browser-to-ledger regression, full disposable PostgreSQL QA, online/offline generated-artifact browser journeys, screenshot artifact upload, and cleanup.
- [StudyHub Library Flow run 42000088504](https://github.com/apexstudying-cmd/prepza/actions/runs/42000088504) was skipped by workflow conditions; it is not a pass.

The CI checks above ran on the PR head immediately before squash merge, not on the new squash-merge SHA itself. They cover the Login extraction and the workflows named; they do not complete the remaining frontend/backend architecture refactor or certify live third-party provider behavior.


## 2026-11-05 — authentication flow extraction (PR #66)

PR #66 moved ForgotPasswordScreen, ResetPasswordScreen, VerifyConfirmScreen, SignupScreen, and CheckEmailScreen into frontend/src/screens/auth/AuthScreens.tsx. The original component bodies were compared against the previous main source and preserved byte-for-byte after normalizing only export declarations and narrowed navigation callback types. Route IDs remain in App.tsx.

The first frontend CI run exposed that tools/apply_unique_usernames.py still expected Signup markup inline in App.tsx. The transform was corrected to target the extracted module when present while retaining the legacy inline fallback; dedicated tests cover both ownership modes and idempotence. The Morio identity contract was also updated to count brand marks in the new auth module.

Evidence on PR head 9e7ce5aafd4fc4ef347f018e25ca40ce626a3f0a: Frontend Build [42001807537](https://github.com/apexstudying-cmd/prepza/actions/runs/42001807537), Student Frontend Contract [42001807515](https://github.com/apexstudying-cmd/prepza/actions/runs/42001807515), and Release Browser/Cross-System Regression [42001807738](https://github.com/apexstudying-cmd/prepza/actions/runs/42001807738) passed. PR #66 was squash-merged as 29b582b6ca9e47b8a0cd725673c6be76b71358a1. The full release run passed production image build, disposable PostgreSQL migrations/ledger, responsive browser checks, B2B browser-to-ledger regression, full disposable PostgreSQL QA, and online/offline generated-artifact browser journeys. StudyHub Library Flow was skipped by workflow conditions and is not counted as passing.

## 2026-11-05 — Chat Options extraction (PR #67; verification pending)

PR #67 moves the existing ChatOptionsScreen into frontend/src/screens/chat/ChatOptionsScreen.tsx, moves MessageAttachmentData, ChatMessageData, and ChatDetail to frontend/src/types/chat.ts, and extracts the existing Avi avatar primitive to frontend/src/ui/Avi.tsx so the screen no longer depends on an undeclared app-shell component. The original 331-line screen body compares byte-for-byte after normalizing the module signature and two explicit dependency injections. CI initially exposed the implicit Avi dependency; it has now been extracted as the same visual component. Verification on the latest PR head is still running; no pass is claimed yet.
