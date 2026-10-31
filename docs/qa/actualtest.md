# Prepza — Actual QA Test Record

## Current PR verification — 2026-10-31 (Social follow screen extraction)

Draft [PR #64](https://github.com/apexstudying-cmd/prepza/pull/64), application-code head `b51e7c4623423bee92234ea4ff9a2dc3482e35b2`, moves the existing `FollowListScreen` (followers/following modes) and `FollowRequestsScreen` into `frontend/src/screens/social/FollowScreens.tsx`. The shared `FollowListUser`, `FollowRequestItem`, and `MessageRequestItem` declarations move to `frontend/src/types/social.ts`; the Chats screen imports the same request type contracts.

- Direct comparison against the original `main` source confirms both screen component bodies are unchanged. Only the module signatures, narrower navigation callback types, named exports, and injected existing app-shell `EmptyState` prop differ.
- Route IDs `followers`, `following`, and `follow-requests` remain in `App.tsx`; route composition passes the same active profile IDs and callbacks.
- Existing API endpoint strings, HTTP methods, CSRF header, follow/unfollow state transitions, pending-request handling, request accept/decline behavior, loading/error states, navigation targets, and screen markup remain unchanged.
- The focused social module contract test was written before implementation; its structural checks failed against the pre-extraction source as expected. The final test suite now passes.
- No backend, database, authorization, product-rule, or persistence behavior is changed.

**Frontend Build:** [run 41237822214](https://github.com/apexstudying-cmd/prepza/actions/runs/41237822214) passed on exact application-code head `b51e7c4623423bee92234ea4ff9a2dc3482e35b2`.
- 35 frontend source-transform/module contract tests passed.
- 5 offline Library patch regression tests passed.
- TypeScript typecheck passed.
- Service-worker JavaScript validation passed.
- Vite production build and launch/architecture audits passed.

**Release Browser and Cross-System Regression:** [run 41237822198](https://github.com/apexstudying-cmd/prepza/actions/runs/41237822198) passed on the same exact code head.
- Production app image built; disposable PostgreSQL and Redis started.
- Alembic migrations and controlled SQL migration ledger passed.
- Mobile and tablet responsive browser checks passed.
- B2B browser-to-ledger metering regression passed.
- Full disposable PostgreSQL QA suite: **98 passed, 0 failed** (3,536 warnings).
- Online/offline and generated-artifact browser journeys passed.
- Responsive screenshots uploaded and disposable services stopped.

Other same-head workflows passed: Admin Route Contract, Student Contract, Student Frontend Contract, AI Economics, AI Generation Architecture, B2B Contract, E2EE Security, E2EE Chat, Study Navigation, and Prepza Control API. StudyHub Library Flow was skipped by its workflow conditions; no claim is made that this separate workflow ran.

**Merge status:** PR #64 remains a draft pending final review and merge. These results are PR-head evidence, not post-merge verification. No external provider behavior (Paystack, SES, OpenAI, R2, or GPU inference) is certified by these tests.

