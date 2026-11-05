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

## 2026-11-05 — Chat Options extraction (PR #67; verified and merged)

PR #67 moves the existing ChatOptionsScreen into frontend/src/screens/chat/ChatOptionsScreen.tsx, moves MessageAttachmentData, ChatMessageData, and ChatDetail to frontend/src/types/chat.ts, and extracts the existing Avi avatar primitive to frontend/src/ui/Avi.tsx so the screen no longer depends on an undeclared app-shell component. The original 331-line screen body compares byte-for-byte after normalizing the module signature and two explicit dependency injections. CI initially exposed the implicit Avi dependency; it has now been extracted as the same visual component. Verification passed on tested code head d19403803c3d8c851af2fbb6df5c8c8e6d73dcfc. Frontend Build [42003751611](https://github.com/apexstudying-cmd/prepza/actions/runs/42003751611) passed 50 source/module tests, 5 offline Library tests, TypeScript, production Vite build, functional wiring, offline/calling architecture, and launch-wiring audits. Student Frontend Contract [42003751434](https://github.com/apexstudying-cmd/prepza/actions/runs/42003751434), Student Contract [42003751659](https://github.com/apexstudying-cmd/prepza/actions/runs/42003751659), E2EE Security [42003751463](https://github.com/apexstudying-cmd/prepza/actions/runs/42003751463), E2EE Chat [42003751612](https://github.com/apexstudying-cmd/prepza/actions/runs/42003751612), B2B Contract [42003751503](https://github.com/apexstudying-cmd/prepza/actions/runs/42003751503), AI Economics [42003751473](https://github.com/apexstudying-cmd/prepza/actions/runs/42003751473), AI Generation Architecture [42003751575](https://github.com/apexstudying-cmd/prepza/actions/runs/42003751575), Admin Route Contract [42003751456](https://github.com/apexstudying-cmd/prepza/actions/runs/42003751456), Study Navigation [42003751472](https://github.com/apexstudying-cmd/prepza/actions/runs/42003751472), Prepza Control API [42003751592](https://github.com/apexstudying-cmd/prepza/actions/runs/42003751592), and Release Browser/Cross-System Regression [42003751401](https://github.com/apexstudying-cmd/prepza/actions/runs/42003751401) passed. The release run passed production image build, disposable PostgreSQL/Redis, Alembic migrations and SQL ledger, mobile/tablet browser checks, B2B browser-to-ledger regression, full disposable PostgreSQL QA, online/offline generated-artifact journeys, screenshot upload, and cleanup. StudyHub Library Flow [42003751683](https://github.com/apexstudying-cmd/prepza/actions/runs/42003751683) was skipped by workflow conditions and is not counted as passing. Documentation-only commits followed the tested code head; no application code changed after the tested head. PR #67 was squash-merged to main as 62cdf80f2652746593b58f131c939f95442b0446.


## 2026-11-05 — XP Progress screen extraction (PR #68)

PR #68 moves the active XPProgressScreen from frontend/src/App.tsx to frontend/src/screens/gamification/ProgressScreens.tsx. XP response types now live in frontend/src/types/gamification.ts. The existing formatStudyTime helper is moved unchanged to frontend/src/lib/studyTime.ts because the Profile screen still uses it. The original 141-line XP component body and formatter were compared byte-for-byte with the prior main source after normalizing only the export and narrower navigation callback type.

- Frontend Build [run 42006708377](https://github.com/apexstudying-cmd/prepza/actions/runs/42006708377): passed 53 source/module tests, 5 offline Library tests, functional wiring audit, ORM/schema drift audit, TypeScript, service-worker JavaScript validation, and production build.
- Student Frontend Contract [run 42006708434](https://github.com/apexstudying-cmd/prepza/actions/runs/42006708434), Student Contract [run 42006708489](https://github.com/apexstudying-cmd/prepza/actions/runs/42006708489), Admin Route Contract [run 42006708384](https://github.com/apexstudying-cmd/prepza/actions/runs/42006708384), B2B Contract [run 42006708298](https://github.com/apexstudying-cmd/prepza/actions/runs/42006708298), AI Economics [run 42006708562](https://github.com/apexstudying-cmd/prepza/actions/runs/42006708562), AI Generation Architecture [run 42006708657](https://github.com/apexstudying-cmd/prepza/actions/runs/42006708657), E2EE Security [run 42006708772](https://github.com/apexstudying-cmd/prepza/actions/runs/42006708772), E2EE Chat [run 42006708473](https://github.com/apexstudying-cmd/prepza/actions/runs/42006708473), Study Navigation [run 42006708393](https://github.com/apexstudying-cmd/prepza/actions/runs/42006708393), and Prepza Control API [run 42006708504](https://github.com/apexstudying-cmd/prepza/actions/runs/42006708504): passed.
- Release Browser/Cross-System Regression [run 42006708497](https://github.com/apexstudying-cmd/prepza/actions/runs/42006708497): passed production image build, disposable PostgreSQL/Redis, Alembic migrations and SQL ledger, responsive mobile/tablet checks, B2B browser-to-ledger regression, full disposable PostgreSQL QA (98 passed), online/offline Study Hub and generated-artifact browser journeys, screenshot upload, and cleanup.
- StudyHub Library Flow [run 42006708366](https://github.com/apexstudying-cmd/prepza/actions/runs/42006708366) was skipped by workflow conditions and is not represented as a pass.

Route audit: the existing study-streak and time-studied route cases render StudyActivityScreen. The older inline StudyStreakScreen and TimeStudiedScreen declarations were left in App.tsx and were not reconnected or deleted. The XP route remains unchanged. These checks do not claim full frontend refactor completion or live third-party provider verification.


### Post-merge status — PR #68

PR #68 was squash-merged to main as 74dcebce5dd05ad08b5e3d77007cc5205f0b7bc0. The tested application-code head was cc665bce25bb570abe659d33e675b5f8acba690a; subsequent commits in the PR changed documentation only. The verified XP Progress screen extraction is now on main. The CI evidence above is from the exact tested PR head; no separate post-merge workflow run is claimed here.


## 2026-11-05 — backend shared-extension boundary (PR #70; pending verification)

The first backend refactor slice creates `extensions.py` with one shared SQLAlchemy extension and explicit `init_extensions(app)`. `app.py` imports and initializes that object after setting its existing configuration, so existing `from app import db` consumers retain their public import path. `db_runtime.py` no longer monkey-patches SQLAlchemy's constructor; the existing PostgreSQL pool defaults and SQLite/missing-URI behavior are retained.

Focused contract tests and a dedicated CI workflow were added for extension initialization and configuration precedence. Backend Shared Extension Contract [run 42010022947](https://github.com/apexstudying-cmd/prepza/actions/runs/42010022947) passed all six focused tests and compilation. Release Browser/Cross-System Regression [run 42010022682](https://github.com/apexstudying-cmd/prepza/actions/runs/42010022682) passed production image, disposable database/migrations, responsive browser checks, B2B metering, full PostgreSQL QA, online/offline generated-artifact journeys, screenshot upload, and cleanup. StudyHub Library Flow was skipped by workflow conditions and is not counted as a pass. This change does not move models/routes, alter schema, or introduce an app factory.


Focused verification update: Backend Shared Extension Contract [run 42010022947](https://github.com/apexstudying-cmd/prepza/actions/runs/42010022947) passed on the application-code head `606481cc09f0db8ed945533cff38e0f39b3ac938`, including dependency installation, Python compilation, and all six focused contract tests. The first attempt [run 42009691957](https://github.com/apexstudying-cmd/prepza/actions/runs/42009691957) failed because the focused test environment omitted the PostgreSQL DBAPI driver; the workflow was corrected to install the pinned `psycopg2-binary` dependency. Full Release Browser/Cross-System Regression [run 42010022682](https://github.com/apexstudying-cmd/prepza/actions/runs/42010022682) remains in progress; PR #70 is not ready to merge until it passes.


PR #70 verification is complete. The exact application source was tested by the focused extension workflow and full release regression; subsequent branch changes were documentation-only. The first focused attempt omitted the PostgreSQL DBAPI driver, which was added to the workflow before the passing rerun.


### Post-merge status — PR #70

PR #70 was squash-merged to main as 907658079a63a61439b42ea7de33d46ca31d0658. Backend Shared Extension Contract [42010022947] passed all six tests and compilation; Release Browser/Cross-System Regression [42010022682] passed production image, database/migrations, responsive browser, B2B metering, PostgreSQL QA, online/offline generated-artifact journeys, screenshot upload, and cleanup. StudyHub Library Flow was skipped by workflow conditions and is not counted as a pass. No separate post-merge workflow run is claimed.

## 2026-11-05 — Library and Notifications full-stack extraction (PR #69; verified and merged)

The existing Library extraction PR was consolidated with the active Notifications screen and its backend HTTP routes. The Notifications frontend module receives the existing app-shell EmptyState and delayed loading composition through props, retains the same state/cache/API/navigation contracts, and has its response type in `frontend/src/types/notifications.ts`. The backend's five existing notification handlers and serializer are moved to `notification_routes.py`, registered at the same app initialization location with explicit dependencies. The original 76-line UI body and 110-line backend handler block compare byte-for-byte after only module signatures and the documented UI/dependency injection/indentation changes.

The initial frontend-only combined PR head passed 65 source/module tests, 5 offline Library tests, typecheck and production build; its full Release Browser/Cross-System Regression passed 98/98 disposable PostgreSQL QA and online/offline browser journeys. That evidence predates the backend route extraction and is not counted as final-head verification. The branch is being reconciled with current main (including PR #70's shared SQLAlchemy extension); new Frontend Build, contract, and full release-browser evidence is required before merge.


## 2026-11-05 — Library and Notifications full-stack extraction (PR #69; final-head verification passed)

Tested application-code head: `0f61c64793cc32befb8ea22ba8ffedf68ef12412`, rebuilt on current main with PR #70's shared SQLAlchemy extension preserved. The active Library screen and Notifications screen are in feature-owned frontend modules. Notification response types live in `frontend/src/types/notifications.ts`; the five Flask notification handlers and serializer live in `notification_routes.py`. Existing UI route IDs, API URLs, methods, CSRF headers, module-level cache, optimistic state changes, route destinations, server-side authentication/ownership checks, endpoint names, response fields, and 24-hour announcement ordering were preserved. The original 76-line screen and 110-line backend route block compare byte-for-byte after the documented signature/prop injection and registrar indentation changes.

- Frontend Build [42014965585]: 69 source/module tests, 5 offline Library tests, functional wiring audit, ORM/schema drift audit, TypeScript, service-worker validation, and production build passed.
- Student Frontend [42014965317], Student Contract [42014965345], Admin Route [42014965329], E2EE Security [42014965431], E2EE Chat [42014965239], B2B [42014965382], AI Economics [42014965486], AI Generation Architecture [42014965230], Prepza Control API [42014965409], Study Navigation [42014965246], Study Hub Runtime [42014965289], and Backend Shared Extension Contract [42014965594] passed.
- Release Browser/Cross-System Regression [42014965433] passed production image, PostgreSQL/Redis, Alembic migrations and controlled SQL ledger, responsive mobile/tablet browser checks, B2B browser-to-ledger metering, 98/98 disposable PostgreSQL QA tests, online/offline Study Hub and generated-artifact journeys, screenshot upload, and service cleanup.
- StudyHub Library Flow [42014965411] was skipped by workflow conditions; it is not counted as a pass.

PR #69 was the single cohesive review for this Library + Notifications extraction and was squash-merged to main as `9a937eaca65f8995de5dc20cb3876577cc133445` after final-head checks passed. No live Paystack, SES, OpenAI, R2, or GPU provider check is implied.

## 2026-11-05 — Public academic catalog route extraction (PR #73)

The public university and program lookup handlers were moved from `app.py` to `academic_catalog_routes.py`. The registrar receives the existing Flask app and University/Program model classes explicitly; it does not import `app.py`. It registers the same paths and GET methods with the original Flask endpoint names `list_universities` and `list_programs`. The handler bodies compare byte-for-byte against the previous main source after removing the registrar indentation.

The focused route contract [42019950835](https://github.com/apexstudying-cmd/prepza/actions/runs/42019950835) passed Python compilation and all five tests. It validates active university/program filtering, alphabetical ordering, the existing missing/inactive-university 404 response, response JSON shapes, endpoint names, and route registration position.

On tested application-code head `55fbf1ce588c6650b5171bd4c752e10055614df7`, Student Frontend [42019950427], Admin Route [42019950566], B2B [42019950492], E2EE Security [42019950395], Study Navigation [42019950431], Prepza Control API [42019950757], AI Economics [42019950545], and Kokoro Python syntax [42019950385] passed.

Release Browser/Cross-System Regression [42019950561](https://github.com/apexstudying-cmd/prepza/actions/runs/42019950561) passed production image build, disposable PostgreSQL/Redis, Alembic migrations and the controlled SQL migration ledger, application startup, mobile/tablet responsive checks, B2B browser-to-ledger metering, 98/98 PostgreSQL QA tests, online/offline Study Hub and generated-artifact browser journeys, screenshot upload, and disposable service cleanup. This PR makes no schema, migration, permission, signup, or model changes. It extracts only two public read-only route handlers.

### Post-merge status — PR #73

PR #73 was squash-merged to `main` as `d57cfecde2c98b59eec867c70cca4270ed2b1e73`. The code tested on head `55fbf1ce588c6650b5171bd4c752e10055614df7` is the merged application code; the subsequent PR commits before merge only updated documentation. The focused contract and full release regression evidence above are from the tested code head. No separate post-merge workflow is claimed.

## 2026-11-05 — Academic catalog ORM model extraction (PR #74)

The existing `University` and `Program` SQLAlchemy class definitions were moved from `app.py` into `academic_models.py`. The module imports the shared `db` instance from `extensions.py`; `app.py` imports both names at the original declaration position after `User` and before `ContentItem`. This keeps the legacy `from app import University, Program` symbol exports while moving ownership. The original model class block (864 characters) was compared byte-for-byte against the extracted module definitions.

Focused model tests protect the shared metadata object, exact table names, column types/lengths/nullability, uniqueness/defaults, the Program foreign-key target, and app compatibility/declaration order. Backend Shared Extension Contract [42021795293](https://github.com/apexstudying-cmd/prepza/actions/runs/42021795293) passed py_compile and 10/10 tests (the six prior extension tests plus four new model tests).

On tested code head `f7c8ec327483f4d5170bfa0aa4ec60285d81574f`, Student Frontend [42021795416], Student Contract [42021795394], Admin Route [42021795332], B2B [42021795333], E2EE Security [42021795546], E2EE Chat [42021795286], Study Navigation [42021795308], Prepza Control API [42021795303], AI Economics [42021795374], AI Generation Architecture [42021795427], and Kokoro Python syntax [42021795321] passed.

Release Browser/Cross-System Regression [42021795474](https://github.com/apexstudying-cmd/prepza/actions/runs/42021795474) passed production image build, disposable PostgreSQL/Redis, Alembic migrations and controlled SQL ledger, app startup, mobile/tablet responsive checks, B2B browser-to-ledger metering, 98/98 PostgreSQL QA tests, online/offline Study Hub and generated-artifact browser journeys, screenshot upload, and cleanup. StudyHub Library Flow [42021795345](https://github.com/apexstudying-cmd/prepza/actions/runs/42021795345) was skipped by workflow conditions and is not represented as a pass.

No model schema or migration changed. At this tested source head, `app.py` has 57 inline `db.Model` declarations and `academic_models.py` owns two; both still register on the same 59-model metadata. Route ownership and all 156 route registrations are unchanged by this model-only slice.

### Post-merge status — PR #74

PR #74 was squash-merged to `main` as `6b82aba7bd7d167488c4a0e9921be6deb50a7648`. The code tested on head `f7c8ec327483f4d5170bfa0aa4ec60285d81574f` is the merged application source; the subsequent commits before merge changed documentation only. The focused 10-test backend extension/model contract and full release browser evidence above are from that tested source head. No separate post-merge workflow is claimed.


## 2026-11-05 — Morio AI Tutor screen extraction (PR #75)

The existing AITutorScreen is now owned by `frontend/src/screens/tutor/AITutorScreen.tsx`. The document picker and conversation UI, TutorMsg/PickableDoc contracts, and the module-scoped `AI_TUTOR_CACHE` moved together. The `ai-tutor` route and app-shell navigation callbacks remain unchanged. The shell-owned error and skeleton components are injected as typed props, so the screen does not import App.tsx or duplicate generic UI.

The original 183-line component body was compared directly with the previous main source. It is byte-for-byte identical after normalizing the export declaration, narrowing the screen callback to its existing `home` and `upload` destinations, and adding only the three existing app-shell components as props. No tutor API URL/method, CSRF header, JSON body, heartbeat cadence, rate-limit/budget message, document filtering rule, UI markup or state transition was intentionally changed.

Evidence on tested code head `f5f8afb34a8d74c742de4b4d33762ec882b05a81`:
- Frontend Build [42022943650](https://github.com/apexstudying-cmd/prepza/actions/runs/42022943650) passed the source/module contracts, offline Library regression, functional wiring and ORM/schema audits, TypeScript, service-worker validation and production build.
- Student Frontend [42022943640](https://github.com/apexstudying-cmd/prepza/actions/runs/42022943640), Student Contract [42022943669](https://github.com/apexstudying-cmd/prepza/actions/runs/42022943669), Admin Route [42022943910](https://github.com/apexstudying-cmd/prepza/actions/runs/42022943910), B2B [42022943975](https://github.com/apexstudying-cmd/prepza/actions/runs/42022943975), E2EE Security [42022943817](https://github.com/apexstudying-cmd/prepza/actions/runs/42022943817), E2EE Chat [42022943967](https://github.com/apexstudying-cmd/prepza/actions/runs/42022943967), AI Economics [42022943628](https://github.com/apexstudying-cmd/prepza/actions/runs/42022943628), AI Generation [42022943687](https://github.com/apexstudying-cmd/prepza/actions/runs/42022943687), Study Navigation [42022943704](https://github.com/apexstudying-cmd/prepza/actions/runs/42022943704), and Prepza Control API [42022943818](https://github.com/apexstudying-cmd/prepza/actions/runs/42022943818) passed.
- Release Browser/Cross-System Regression [42022943630](https://github.com/apexstudying-cmd/prepza/actions/runs/42022943630) passed the production image, disposable database/migration ledger, responsive browser checks, B2B ledger regression, 98/98 PostgreSQL QA, online/offline and generated-artifact journeys, screenshot upload, and cleanup.
- StudyHub Library Flow [42022943808](https://github.com/apexstudying-cmd/prepza/actions/runs/42022943808) was skipped by workflow conditions and is not counted as a pass.

The verification is scoped to the tested PR head; subsequent PR changes are documentation-only. This extraction does not complete the remaining chat, document study/reader, admin or app-navigation boundaries.


## 2026-11-05 — Splash and Edit Profile extraction (PR #77; current PR head)

The existing SplashScreen and EditProfileScreen component bodies were moved into their feature-owned modules. Direct source comparison against base main confirms both bodies are byte-for-byte identical after normalising only module exports, the explicit splash brandline prop, narrower navigation callback types, and the local EditProfileMe response contract. App.tsx now contains only the imports and route composition for these screens.

The Study Navigation prebuild transformer was updated for the new SplashScreen ownership boundary. The app shell supplies the offline-resume callback; SplashScreen does not import App.tsx or duplicate navigation-state parsing. The transform handles both inline legacy and extracted module modes and re-applies idempotently even when the existing marker is already present. The production-build verifier and workflow anchors now inspect the extracted module.

Frontend Build [42030603950](https://github.com/apexstudying-cmd/prepza/actions/runs/42030603950) passed 76 frontend source/module tests, 5 offline Library tests, TypeScript, service-worker validation, production Vite build, and architecture audits. Student Frontend [42030604065], Student Contract [42030603908], Admin Route [42030604002], B2B [42030603900], AI Generation [42030604051], AI Economics [42030604139], Prepza Control API [42030603917], E2EE Security [42030603959], and E2EE Chat [42030604078] passed.

The full Release Browser/Cross-System Regression [42030603969](https://github.com/apexstudying-cmd/prepza/actions/runs/42030603969) passed: production app image; disposable PostgreSQL/Redis; all 43 migration files and controlled SQL ledger; app startup; mobile/tablet responsive browser checks; B2B browser-to-ledger metering; 98/98 disposable PostgreSQL QA tests; online/offline Study Hub and generated-artifact journeys; screenshot upload; and cleanup. StudyHub Library Flow was skipped by workflow conditions and is not counted as passing. Subsequent PR commits update documentation only; no application source changed after the tested code head.

No API, authentication, authorization, database, product-rule, screen-design, or business-logic rewrite was included. The refactor remains incomplete: ChatDetail/Chats, DocumentStudy/Reader, AdminSection, generation flows, Podcast Player, Home/Explore and app-shell boundaries still require dependency mapping and behavior contracts.


### New Chat extraction follow-up — PR #77

NewChatScreen now lives in frontend/src/screens/chat/NewChatScreen.tsx (159 lines). App.tsx is 11,440 lines on this branch, down 413 lines from the original 11,853-line baseline. The moved component body was directly compared with base main and matched byte-for-byte after normalising only its module export and narrowed navigation callback type.

The added contract protects the existing 300 ms debounced student search and cleanup, direct chat create/reuse, group-name/member validation and creation, CSRF headers, selected participant state, and chat-detail navigation. The latest Frontend Build [42031983870] passed 78 source/module tests, 5 offline Library tests, TypeScript, service-worker validation, production build, and architecture audits. Student Frontend, Student Contract, Admin Route, B2B, AI, control API, E2EE Chat, and E2EE Security workflows passed on the same code head.

Full Release Browser/Cross-System Regression [42031984075](https://github.com/apexstudying-cmd/prepza/actions/runs/42031984075) passed on the New Chat code head: production app image, disposable PostgreSQL/Redis, all 43 migration files and controlled ledger, mobile/tablet browser checks, B2B browser-to-ledger metering, 98/98 disposable PostgreSQL QA tests, online/offline Study Hub lifecycle and generated-artifact journeys, screenshot upload, and cleanup. Subsequent PR commits update documentation only.
