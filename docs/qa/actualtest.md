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


### Time Studied and Share Opportunity extractions — PR #77

TimeStudiedScreen is now in frontend/src/screens/gamification/TimeStudiedScreen.tsx (61 lines), and ShareOppForm is now in frontend/src/screens/opportunities/ShareOppForm.tsx (45 lines). Together these remove 94 lines from App.tsx. Both component bodies were compared directly against base main and are byte-for-byte identical after normalising only module exports and narrowed navigation callback types.

Focused contracts cover the existing day/week/month study-time selection, API loading and cancellation, formatted duration, profile navigation, opportunity form fields/category choices, controlled description, and existing back/post navigation. Frontend Build [42034151911](https://github.com/apexstudying-cmd/prepza/actions/runs/42034151911) and Release Browser/Cross-System Regression [42034151448](https://github.com/apexstudying-cmd/prepza/actions/runs/42034151448) are running against the latest code head; their results are pending.


### Student Profile extraction follow-up — PR #77

StudentProfileScreen and its PublicProfile/FollowSummary response types now live in frontend/src/screens/profile/StudentProfileScreen.tsx (164 lines). App.tsx is 11,286 lines on this branch, 567 fewer than the 11,853-line baseline. Direct comparison against base main confirms the component body is byte-for-byte identical after normalising only the module export and narrowed callback/back-screen types.

The new contract protects public-profile and follow-summary requests, privacy handling, follow/unfollow and pending states, direct chat creation, chat-options navigation, and the XP/follower/document/study-time summary. The existing App back-screen state was narrowed to the only two values actually used: chat-detail and chats.

Frontend Build [42033518073] passed 80 source/module tests, 5 offline Library tests, TypeScript, service-worker validation, production build, and architecture audits. Student Frontend, Student Contract, Admin Route, B2B, AI, Prepza Control API, and E2EE Chat workflows passed. Full Release Browser/Cross-System Regression [42033518119] and E2EE Security Regression [42033518226] were still running at the time of this note; their success is required before merge.


### Study Streak extraction — PR #77

StudyStreakScreen and its local streak response types are now in frontend/src/screens/gamification/StudyStreakScreen.tsx (214 lines), removing 205 lines from App.tsx. The moved component body was compared with base main and matched byte-for-byte after normalising only the module export and callback type. Focused contracts protect month-scoped /streak requests, cancellation, day selection, month navigation, milestone display, duration formatting, and both existing back/share destinations.

The previous CI pass exposed one missing callback destination in the earlier TimeStudiedScreen extraction: the existing share-sheet action had not been included in the narrowed callback type. That type and its test were corrected without changing the component body. Latest Frontend Build [42034876037](https://github.com/apexstudying-cmd/prepza/actions/runs/42034876037) passed on the corrected Study Streak code head: 86 frontend source/module contract tests, 5 offline Library tests, TypeScript, service-worker validation, production Vite build, architecture audits, and launch-wiring verification. Full Release Browser/Cross-System Regression [42034875673](https://github.com/apexstudying-cmd/prepza/actions/runs/42034875673) is still queued/in progress on that same application-code head; release verification remains pending.


### Profile screen extraction — PR #77

ProfileScreen now lives in frontend/src/screens/profile/ProfileScreen.tsx (179 lines), with its PROFILE_CACHE moved into the same feature module. Shared ProfileMe and HomeDocument contracts moved to frontend/src/types/profile.ts; GamificationSummary moved to frontend/src/types/gamification.ts. App.tsx retains route dispatch, the existing SkeletonProfile implementation and parent-owned state, passing the skeleton as a component prop.

The ProfileScreen component body was directly compared with base main and is byte-for-byte identical after normalising only its export, explicit SkeletonProfile prop and narrowed route callback type. Source contracts protect the /me, gamification, achievements, study-time, follow-request, saved-opportunity and documents requests; tab selection/cancellation; university/program lookup; cached profile state; and existing navigation. Frontend Build [42036291254](https://github.com/apexstudying-cmd/prepza/actions/runs/42036291254) passed on the ProfileScreen code head: 88 frontend source/module contract tests, 5 offline Library tests, TypeScript, service-worker validation, production build, architecture audits and launch-wiring verification. The first typecheck found that dynamic profile-card destinations were still cast to the App-local Screen type; these are now represented by a local ProfileScreenRoute union with the same destinations. Full Release Browser/Cross-System Regression [42036291297](https://github.com/apexstudying-cmd/prepza/actions/runs/42036291297) and remaining workflows are queued on this code head.


### Document Ready extraction — PR #77

DocReadyScreen now lives in frontend/src/screens/study/DocReadyScreen.tsx (73 lines). Its shared DocumentDetail response contract moved to frontend/src/types/documents.ts. App.tsx still owns the route and passes the existing TopBar component into the extracted module. The screen body was compared directly with base main and matches byte-for-byte after normalising only the module export, injected TopBar, and local route-union type. Source contracts protect the document details request, metadata display, error message, and all seven existing study/action destinations. Frontend Build [42036938429](https://github.com/apexstudying-cmd/prepza/actions/runs/42036938429) passed on code head 74b8fac: 90 frontend source/module contract tests, 5 offline Library tests, TypeScript, service-worker validation, production build, architecture audits and launch-wiring verification. Full Release Browser/Cross-System Regression [42036938563](https://github.com/apexstudying-cmd/prepza/actions/runs/42036938563) and remaining workflows are queued on this code head.


## 2026-11-09 — Consolidated public-shell route contract (PR #77; pre-verification snapshot)

The public shell route move from the former PR #76 branch has been applied to the consolidated frontend integration branch. `public_shell_routes.py` registers `/`, `/sw.js`, and `/health` with explicit dependencies; `app.py` retains the global Flask entry point and registers the module after `track_last_active` and before academic catalog routes. Added focused test-client contracts cover original paths/methods/endpoint names, index serving, service-worker MIME/cache headers, health SQL probe and safe sweep, limiter exemption, and the 503 failure response.

This paragraph records the state before final CI completed and is superseded by the exact-head verification closeout below. StudyHub Library Flow remains conditional; its skipped run is not counted as a pass.

PR #76 is now closed as superseded, not merged. Its implementation is represented in consolidated PR #77; all verification claims must refer to the final combined PR #77 head.

## 2026-11-09 — Consolidated refactor verification closeout

Verified against the exact PR #77 head `b37cad55f3fb6e389dead1d4ca19df2f31265674` (base `main` at `459c96cd7179810499edbec266e1f5deab3f9d4c`). PR #77 contains 30 changed files (+2,191/−1,236 lines) and remains open, unmerged, and mergeable. On this exact head, 16 GitHub Actions workflows passed: Frontend Build; Study Navigation Polish; Student Frontend Contract; Student Contract Validation; Admin Route Contract; Prepza Control API; Backend Shared Extension Contract; Backend Academic Catalog Route Contract; B2B Contract Validation; AI Generation Architecture; AI Economics Validation; E2EE Chat Validation; E2EE Security Regression; Study Hub Runtime Regression; Kokoro GPU Worker Validation; and Release Browser and Cross-System Regression. (The workflow inventory contains 16 successful runs plus one skipped run.)

Release Browser and Cross-System Regression [run 42581515451](https://github.com/apexstudying-cmd/prepza/actions/runs/42581515451) passed on this exact SHA: production image build; disposable PostgreSQL/Redis startup; Alembic migrations and controlled migration-ledger checks; app startup; mobile/tablet responsive browser checks; B2B browser-to-ledger metering regression; full disposable PostgreSQL QA; online/offline and generated-artifact browser journeys; responsive screenshot upload; and service cleanup. The separate StudyHub Library Flow [run 42581515401](https://github.com/apexstudying-cmd/prepza/actions/runs/42581515401) was skipped by workflow conditions and is not counted as a pass. The failure-log collection step was skipped because the job succeeded.

At this exact PR head, `frontend/src/App.tsx` is 10,745 lines and `app.py` is 10,139 lines. This is a structural refactor, not completion of all repository modularization: both root files remain substantial and further bounded extraction can continue later. No production deployment, live provider verification, or production-database migration is implied by these CI results.

PR #77 remains open and unmerged. These checks verify the integration branch only; `main` does not contain these changes until the PR is merged. Do not merge without the user's explicit approval.

## 2026-11-09 — Admin feature extraction and exact-head verification (PR #77)

The admin feature is now owned by four modules: `frontend/src/admin/AdminPlatform.tsx` (118 lines; navigation shell), `AdminSection.tsx` (1,921 lines; main stateful tabs), `AdminPanels.tsx` (1,251 lines; independent domain panels), and `AdminShared.tsx` (323 lines; shared types and presentation primitives). `App.tsx` imports the platform module and no longer contains the admin feature implementation. The existing section keys, route dispatch, server-side authorization boundary, API requests, CSRF headers, and state/loading/mutation workflows were retained. The Prepza control settings transformer and its workflow were updated to target the extracted AdminSection module; the Morio icon contract now counts brand marks across feature-owned admin modules.

Verified against PR #77 code head `49e2782b911e154fc649f50d4d0356944fe72d1c` (base `main` at `459c96cd7179810499edbec266e1f5deab3f9d4c`). On this exact code head, 16 workflows passed: [Frontend Build run 42593752541](https://github.com/apexstudying-cmd/prepza/actions/runs/42593752541), [Student Frontend Contract run 42593752484](https://github.com/apexstudying-cmd/prepza/actions/runs/42593752484), [Student Contract Validation run 42593752482](https://github.com/apexstudying-cmd/prepza/actions/runs/42593752482), [E2EE Security Regression run 42593752427](https://github.com/apexstudying-cmd/prepza/actions/runs/42593752427), [E2EE Chat Validation run 42593752428](https://github.com/apexstudying-cmd/prepza/actions/runs/42593752428), [B2B Contract Validation run 42593752475](https://github.com/apexstudying-cmd/prepza/actions/runs/42593752475), [AI Generation Architecture run 42593752464](https://github.com/apexstudying-cmd/prepza/actions/runs/42593752464), [AI Economics Validation run 42593752461](https://github.com/apexstudying-cmd/prepza/actions/runs/42593752461), [Admin Route Contract run 42593752415](https://github.com/apexstudying-cmd/prepza/actions/runs/42593752415), [Prepza Control API run 42593752410](https://github.com/apexstudying-cmd/prepza/actions/runs/42593752410), [Backend Shared Extension Contract run 42593752394](https://github.com/apexstudying-cmd/prepza/actions/runs/42593752394), [Backend Academic Catalog Route Contract run 42593752485](https://github.com/apexstudying-cmd/prepza/actions/runs/42593752485), [Study Navigation Polish run 42593752483](https://github.com/apexstudying-cmd/prepza/actions/runs/42593752483), [Study Hub Runtime Regression run 42593752312](https://github.com/apexstudying-cmd/prepza/actions/runs/42593752312), [Kokoro GPU Worker Validation run 42593752320](https://github.com/apexstudying-cmd/prepza/actions/runs/42593752320), and [Release Browser/Cross-System Regression run 42593752604](https://github.com/apexstudying-cmd/prepza/actions/runs/42593752604).

The full release run passed production image build, disposable PostgreSQL/Redis startup, Alembic migrations and controlled migration-ledger checks, app startup, mobile/tablet responsive browser checks, B2B browser-to-ledger metering, full disposable PostgreSQL QA, online/offline and generated-artifact browser journeys, responsive screenshot upload, and service cleanup. Failure-log collection was skipped because the run succeeded. [StudyHub Library Flow run 42593752545](https://github.com/apexstudying-cmd/prepza/actions/runs/42593752545) was skipped by workflow conditions and is not counted as a pass.

At this code head, `frontend/src/App.tsx` is 5,323 lines (down from 8,903 immediately before the admin extraction, 40.2% smaller); `app.py` remains 9,643 lines. This is improved module ownership and navigation, not completion of repository-wide decomposition. The central `AdminSection.tsx` still owns several stateful tabs and needs careful future per-tab decomposition. No production deployment, live provider verification, or production-database migration is implied by these CI results.

PR #77 remains open and unmerged at the time of this evidence. The user has authorized merging only when the exact final PR head passes the required checks; re-check the head SHA before merging. Main does not contain these changes until merge.

## 2026-11-09 — Shop browse UX remediation (PR #77; verification pending)

After the user's end-to-end feedback that Shop does not look or behave like the rest of Prepza, the first browse-focused remediation was committed on the consolidated PR #77 branch. The listing card changed from a clickable `article` to a semantic, named `button`; Shop navigation and back controls now meet a 44px minimum touch target; browse exposes active filters and a one-tap clear action; filtered-empty results are distinct from an empty marketplace; initial browse loading now has reserved-space skeleton cards; and the header follows the shared Prepza navy/gold shell pattern.

A focused `tests/test_shop_ux_contract.py` covers these source-level expectations and has been added to the Frontend Build test command. Existing browse-cache privacy and request sequencing code is retained. The KES 100/30-day seller fee, manual renewal, provider-authoritative payment verification, no-buyer-checkout rule, seller contact, moderation endpoints and existing API payloads were not intentionally changed.

**Verification state:** No GitHub Actions workflow run or commit status has been returned for the current PR head after these Shop changes. The earlier admin/refactor code head `49e2782b911e154fc649f50d4d0356944fe72d1c` had 16 passing workflows including the full release regression, but that result does not verify the later Shop changes. The new Shop UX contract, TypeScript/build, phone/tablet screenshots and buyer/seller/admin journeys remain pending on the final head. Do not close the Shop UX or release gate yet.

## 2026-11-09 — Shop responsive screenshot review and follow-up (PR #77)

Responsive screenshots from the first refreshed Shop run are available in artifact [prepza-mobile-responsive-screenshots](https://github.com/apexstudying-cmd/prepza/actions/runs/42594995289). The screenshots show the navy/gold header and filters fitting phone and tablet widths without horizontal overflow. They also exposed a one-result grid issue: `auto-fill` kept an unused column, leaving the only listing card narrow. The four 155px Shop listing/skeleton grids now use `auto-fit` to let a single result fill the available width.

The first browser run `42594995289` failed in `scripts/test_browser_mobile_responsive.py` because its text locator still expected the old Shop header tagline. The header refresh had split that copy into a shorter title line and a separate direct-contact statement, and it replaced the visible back text with explicit accessible names. The browser test was updated to assert the new copy and `Back to Home` / `Back to Shop` controls. This run did not reach the later create/payment and stale-cache checks; it is not a full Shop end-to-end pass.

The listing editor is now a semantic form with native required-field validation and one submit handler. Shop buttons keep `type="button"` by default; only the listing-save action is `type="submit"`. Source contracts now cover the form, touch targets, semantic navigation, and responsive single-result grid behavior.

**Current verification:** Full Release Browser/Cross-System Regression run [42595814104](https://github.com/apexstudying-cmd/prepza/actions/runs/42595814104) was started against code head `91ae94195bd21be3142a9216a44bebcea78bc18e`; it was still in progress at this documentation update. Frontend Build and the other PR workflows were queued/in progress on that same code head. These results must be refreshed after the final documentation commits; do not mark Shop UX verified until the final code head has passing Frontend Build and release regression with screenshots.

### Frontend Build result for Shop UX code head

Frontend Build [run 42595814116](https://github.com/apexstudying-cmd/prepza/actions/runs/42595814116) passed on code head `91ae94195bd21be3142a9216a44bebcea78bc18e`: 112 frontend/source-contract tests passed, 5 offline Library regression tests passed, the functional-wiring and ORM/schema drift audits passed, TypeScript completed, service-worker JavaScript validation passed, and the production frontend build passed. This includes the new Shop UX contracts for semantic cards/navigation, filters/empty states, touch targets, responsive single-result grids, and native listing-form validation.

The full Release Browser/Cross-System Regression [run 42595814104](https://github.com/apexstudying-cmd/prepza/actions/runs/42595814104) was still in progress after disposable services and Alembic/migration-ledger checks passed; browser and full database QA stages had not all completed at this note. The successful Frontend Build does not substitute for those runtime checks.

### Responsive browser result — code head `91ae94195bd21be3142a9216a44bebcea78bc18e`

In Release Browser run `42595814104`, the mobile/tablet responsive browser step completed successfully after the Shop header locator updates. This confirms the test reached the refreshed Shop route and completed the existing phone-small, phone-standard and tablet-portrait responsive journey without the earlier stale-copy timeout. The run then advanced to B2B browser-to-ledger metering; full PostgreSQL QA and online/offline generated-artifact journeys were still pending. Final release status remains open until the entire run completes.

### Full disposable PostgreSQL QA result — code head `91ae94195bd21be3142a9216a44bebcea78bc18e`

The full disposable PostgreSQL QA suite in Release Browser run `42595814104` completed successfully after the phone/tablet browser and B2B browser-to-ledger steps passed. The final online/offline and generated-artifact browser journeys were still in progress at this update, followed by screenshot upload and service cleanup. Do not call the overall release regression passed until those remaining steps complete.

## 2026-11-09 — Full refactor/Shop browser regression milestone

Release Browser and Cross-System Regression [run 42595814104](https://github.com/apexstudying-cmd/prepza/actions/runs/42595814104) passed on code head `91ae94195bd21be3142a9216a44bebcea78bc18e`. It completed the production app image build, disposable PostgreSQL/Redis startup, Alembic migrations, controlled migration-ledger checks, app startup, phone-small/phone-standard/tablet-portrait browser checks, B2B browser-to-ledger metering, full disposable PostgreSQL QA, online/offline and generated-artifact browser journeys, responsive screenshot upload, and cleanup. Frontend Build [run 42595814116](https://github.com/apexstudying-cmd/prepza/actions/runs/42595814116) passed 112 source/transform tests, 5 offline Library tests, audits, TypeScript and production build. The other 15 PR workflows on this exact code head passed; StudyHub Library Flow was skipped and is not counted as a pass.

A further screenshot review then found that the fixed global bottom navigation could obscure lower Shop content on the shortest phone viewport. Shop now reserves safe-area-aware bottom scroll space, and the responsive browser test scrolls the seller's `Save & publish` action into view and checks that it clears the fixed nav. This is a new code change after `91ae941`; the follow-up Frontend Build and Release Browser runs on code head `d1a5fd8adb49aff443f7578d861b5cf7c7014d65` are queued. The successful `91ae941` run does not verify that later bottom-nav fix.

### Bottom-navigation clearance Frontend Build — code head `d1a5fd8adb49aff443f7578d861b5cf7c7014d65`

Frontend Build [run 42596828203](https://github.com/apexstudying-cmd/prepza/actions/runs/42596828203) passed on the follow-up Shop code: 114 frontend/source-contract tests, 5 offline Library tests, functional-wiring and ORM/schema audits, TypeScript, service-worker validation and production build. The new contract verifies safe-area-aware bottom padding; the Shop form submit action is now checked by the responsive browser journey for clearance above the fixed global navigation. Release Browser run [42596828231](https://github.com/apexstudying-cmd/prepza/actions/runs/42596828231) is queued on the same code head and must complete before the bottom-navigation fix is called browser-verified.

### Bottom-nav browser assertion harness correction

Release Browser run `42596828231` reached the updated responsive Shop flow and captured the listing form after scrolling. Its screenshots show the `Save & publish` and Cancel actions fully above the fixed global nav on phone-small. The job then failed in the new assertion because Playwright's `bounding_box()` returns `x/y/width/height`, not `top/bottom`; this was a test-harness KeyError on all three viewports, not an overlap assertion failure. The browser check now compares `y + height` with the nav's `y`. Follow-up run on code head `76fcff95c025536ab5e7f6270184d411d92271bd` is pending; do not count the bottom-nav check as passed until that run completes.

### Playwright bounds correction Frontend Build

Frontend Build [run 42597710544](https://github.com/apexstudying-cmd/prepza/actions/runs/42597710544) passed on code head `76fcff95c025536ab5e7f6270184d411d92271bd`: 114 frontend/source-contract tests, 5 offline Library tests, audits, TypeScript, service-worker validation and production build. This validates the code and corrected test syntax; the responsive browser check is still pending in Release Browser run `42597710733`.

### Bottom-nav clearance responsive pass — code head `76fcff95c025536ab5e7f6270184d411d92271bd`

Release Browser run [42597710733](https://github.com/apexstudying-cmd/prepza/actions/runs/42597710733) passed the phone-small, phone-standard and tablet-portrait responsive browser step. The corrected Playwright assertion completed on all three viewports and confirmed the listing editor's `Save & publish` action can be scrolled fully above the fixed global navigation. Production image build, disposable PostgreSQL/Redis startup, Alembic migration and controlled migration-ledger checks also passed. B2B metering, full disposable PostgreSQL QA and online/offline generated-artifact journeys remained in progress at this update.

## 2026-11-09 — AdminSection controller/view split

The admin render layer is now decomposed: `AdminSection.tsx` is 172 lines; `useAdminSectionController.ts` is 934 lines and owns the original state/effects/API/CSRF/mutation logic; `AdminSectionCoreViews.tsx` is 783 lines; and `AdminSectionPlatformViews.tsx` is 368 lines. The view components receive typed `Pick<AdminSectionController, ...>` props and do not import the API client. The controller hook remains unconditional, preserving the previous state/effect lifetime when switching admin tabs.

Focused source-contract tests passed in Frontend Build run `42599305452` (118 source/transform tests and 5 offline Library tests passed). TypeScript then reported two `AdminPayment` type references missing from the new core view module. I added the missing type-only import in commit `82b792a`. Prepza Control API [run 42599433232](https://github.com/apexstudying-cmd/prepza/actions/runs/42599433232) and Backend Shared Extension Contract [run 42599433202](https://github.com/apexstudying-cmd/prepza/actions/runs/42599433202) passed on the controller/view split. **The exact current head still needs a fresh TypeScript/Frontend Build pass**; do not count the admin view split as fully CI-verified yet.

### Bottom-navigation Shop regression complete — code head `76fcff95c025536ab5e7f6270184d411d92271bd`

Release Browser and Cross-System Regression [run 42597710733](https://github.com/apexstudying-cmd/prepza/actions/runs/42597710733) passed all steps on this code head: production image build; disposable PostgreSQL/Redis; Alembic and controlled migration-ledger checks; app startup; phone-small/phone-standard/tablet-portrait responsive journeys including the Shop form action vs fixed bottom-nav assertion; B2B browser-to-ledger regression; full disposable PostgreSQL QA; online/offline and generated-artifact browser journeys; responsive screenshot upload; cleanup. Frontend Build [run 42597710544](https://github.com/apexstudying-cmd/prepza/actions/runs/42597710544) passed 114 frontend/source-contract tests, 5 offline Library tests, audits, TypeScript and production build. The 15 other workflows on that code head passed; StudyHub Library Flow was skipped by workflow conditions and is not counted as a pass.

This verifies the responsive Shop browse/create-form slice and bottom-nav clearance, not every buyer/seller/admin screen. The deeper Shop flow audit (detail, Saved/My Listings, in-app seller contact, report and moderation) remains a follow-up. The later AdminSection view split is after this tested code head and still needs a fresh Frontend Build/TypeScript pass.


## 2026-11-09 — AdminSection controller/view split exact-head verification

The AdminSection split is verified on code head `82b792a64aeec6af70e38e508c44afca33666c1e`. Frontend Build [run 42599433294](https://github.com/apexstudying-cmd/prepza/actions/runs/42599433294) passed, including source contracts, TypeScript and the production build. Release Browser and Cross-System Regression [run 42599433357](https://github.com/apexstudying-cmd/prepza/actions/runs/42599433357) passed its complete job: production image build; disposable PostgreSQL/Redis; Alembic and controlled migration-ledger checks; app startup; phone-small, phone-standard and tablet-portrait browser checks; B2B browser-to-ledger metering; full disposable PostgreSQL QA; online/offline generated-artifact journeys; screenshot upload; and cleanup. The complete workflow inventory has 16 successful workflows and one skipped StudyHub Library Flow workflow, which is not counted as a pass.

The current PR #77 head is `7d6fa6545c8c4bb666a7690e62752eee8ca209e1`. Commits after the tested application-code head contain documentation updates, a comment-only workflow clarification, and no runtime application-code changes. PR #77 remains open and unmerged. This does not verify the remaining end-to-end Shop detail, Saved/My Listings, seller-contact, report and moderation journeys, nor live external providers or production release gates.


## 2026-11-11 — Admin domain-panel extraction — code head `99796c39e81f2ed79949e9b492b31a5541de5d8b`

Frontend Build [run 43001624586](https://github.com/apexstudying-cmd/prepza/actions/runs/43001624586) passed. The source-transform/boundary step passed 120 tests, including the new Admin domain-panel boundary contract and updated legacy Admin ownership contract. The offline Library regression passed 5 tests. Functional-wiring and ORM/schema audits passed, TypeScript passed, service-worker JavaScript validation passed, and the production Vite build completed successfully. The first attempt on the prior code head failed because an older contract expected component implementations to live directly in `AdminPanels.tsx`; the test was updated to validate the compatibility barrel and the new owning modules. The corrected exact-head Frontend Build is green.

At the time of this note, Release Browser and Cross-System Regression [run 43001624499](https://github.com/apexstudying-cmd/prepza/actions/runs/43001624499) had not completed. Do not count this refactor as full release-regression verified until that run and the other relevant PR workflows complete. PR #77 remains open and unmerged.


## 2026-11-11 — Exact-head Release Browser/Cross-System Regression passed

Release Browser and Cross-System Regression [run 43001889849](https://github.com/apexstudying-cmd/prepza/actions/runs/43001889849) passed on exact PR #77 head `949530b97fea9df8557eddbd408f2c667130c511`. The job built the production image; started disposable PostgreSQL/Redis; passed Alembic and controlled migration-ledger checks; passed phone-small (360x800), phone-standard (390x844), and tablet-portrait (768x1024) browser checks; passed B2B browser-to-ledger metering; passed the full disposable PostgreSQL QA suite; passed online/offline Study Hub and generated-artifact journeys; uploaded 12 responsive screenshots (artifact [prepza-mobile-responsive-screenshots](https://github.com/apexstudying-cmd/prepza/actions/runs/43001889849/artifacts/13845874778)); and cleaned up disposable services/volumes. Frontend Build [run 43001890115](https://github.com/apexstudying-cmd/prepza/actions/runs/43001890115) also passed on the same exact head. Of 17 workflows on the head, 16 succeeded and StudyHub Library Flow was skipped by workflow conditions; the skipped workflow is not counted as a pass. This verifies the PR branch, not production deployment or live provider behavior.

The screenshot artifact was downloaded and inspected. It confirms the Shop browse and listing-editor layouts at phone/tablet sizes, including fixed-bottom-navigation clearance. It does not prove Shop visual consistency or all buyer/seller/admin journeys: detail, Saved/My Listings, seller contact, reporting and moderation still need a dedicated browser walkthrough. Shop remains in progress; live Paystack and R2 provider behavior remains unverified. PR #77 remains open and unmerged.


## 2026-11-11 — Podcast Player extraction and Shop role journeys — exact PR #77 head

Exact code head: `76a435d91db27ca09292e20d16c31ec2b34c9884` (PR #77; base `459c96cd7179810499edbec266e1f5deab3f9d4c`). PR #77 remains open and unmerged.

- Podcast Player now lives in `frontend/src/screens/podcast/PodcastPlayerScreen.tsx` (349 lines) with explicit props for the existing app-owned API, offline cache, navigation and activity callbacks. `frontend/src/App.tsx` is 5,034 lines and `app.py` is 9,643 lines at this head. This is a behavior-preserving extraction; it does not finish backend modularization.
- Offline fix: when the browser is offline, the player checks the account-scoped cached audio Blob before consulting a service-worker-cached `ready` descriptor. The descriptor's `audio_url` can still point at the network and is not itself a playable offline asset.
- Release logs confirm podcast activity-credit continuation while hidden, no credit while paused, 12 canonical generated-material GETs cached with server-side private ownership, zero generation POSTs during offline replay, actual cached podcast descriptor + Blob playback offline, and successful reopen after reload.
- Shop visual pass aligns the header/tab hierarchy and listing card typography/image proportions with Prepza's Home language while preserving 44px targets, existing navigation/API and the KES 100 per 30-day seller fee.
- New real-browser Shop journey verifies buyer browse/detail/save/Saved/report/in-app contact/WhatsApp visibility; seller My listings/pause/mark-sold/paid-form disclosure; and admin approve/reject/report resolution/payment-review notes and allow-retry. The moderation approval fixture uses a synthetic uploaded-photo key; no live R2 upload or Paystack transaction is implied.

Frontend Build [run 43023202179](https://github.com/apexstudying-cmd/prepza/actions/runs/43023202179) passed on this exact head. Release Browser and Cross-System Regression [run 43023202418](https://github.com/apexstudying-cmd/prepza/actions/runs/43023202418) passed the production image build, disposable PostgreSQL/Redis, Alembic and controlled ledger, phone/tablet browser checks, Shop role journeys, B2B browser-to-ledger, 99 disposable PostgreSQL QA tests, online/offline Study Hub and generated-artifact journeys, screenshot upload and service cleanup. Sixteen workflows succeeded; StudyHub Library Flow was skipped by workflow conditions and is not counted as a pass. Responsive/Shop screenshots: [artifact 13855748767](https://github.com/apexstudying-cmd/prepza/actions/runs/43023202418/artifacts/13855748767).

Shop remains IN_PROGRESS because live Paystack sandbox and real R2 object/header checks remain unverified. The overall release remains BLOCKED. PR #77 remains unmerged; no deployment, live payment or production-database migration was performed.


## 2026-11-12 — PR #77 merged; exact-head architecture and Shop verification

The consolidated architecture/Shop integration [PR #77](https://github.com/apexstudying-cmd/prepza/pull/77) was squash-merged to main as [48a11afa5ca9b582d656cd83030f5dfefc87e22f](https://github.com/apexstudying-cmd/prepza/commit/48a11afa5ca9b582d656cd83030f5dfefc87e22f). The exact PR code head tested before merge was 3fcc2b3fbd9605c14c22a6b587475a779d559150, based on main 459c96cd7179810499edbec266e1f5deab3f9d4c. This records pre-merge exact-head CI; no separate post-merge CI result is claimed.

### Frontend Build

[Frontend Build run 43024634109](https://github.com/apexstudying-cmd/prepza/actions/runs/43024634109) passed on exact code head:
- 124 frontend/source-transform/module-boundary tests passed.
- 5 offline Library regression tests passed.
- Functional-wiring and ORM/schema drift audits passed.
- TypeScript typecheck passed.
- Service-worker JavaScript validation passed.
- Production Vite build passed.

### Release Browser and Cross-System Regression

[Release Browser run 43024634046](https://github.com/apexstudying-cmd/prepza/actions/runs/43024634046) passed on the same exact code head:
- Production application image built; disposable PostgreSQL and Redis started.
- Alembic migrations and the controlled SQL migration ledger were applied to disposable PostgreSQL; app startup passed.
- Phone-small (360x800), phone-standard (390x844), and tablet-portrait (768x1024) browser checks passed.
- Dedicated Shop buyer, seller and admin browser journeys passed.
- B2B browser-to-ledger metering regression passed.
- Full disposable PostgreSQL QA passed: **99 passed, 0 failed** (3,536 warnings).
- Online/offline Study Hub lifecycle and generated-artifact replay passed, including cached podcast audio Blob playback/reload and zero generation POSTs during offline replay.
- Responsive screenshots uploaded; disposable services/volumes cleaned up.

The workflow inventory for the exact code head contained 16 successful workflows: Frontend Build, Release Browser/Cross-System Regression, Study Navigation Polish, Student Frontend Contract, Student Contract Validation, Admin Route Contract, Prepza Control API, Backend Shared Extension Contract, Backend Academic Catalog Route Contract, B2B Contract Validation, AI Generation Architecture, AI Economics Validation, E2EE Chat Validation, E2EE Security Regression, Study Hub Runtime Regression, and Kokoro GPU Worker Validation. StudyHub Library Flow was conditionally skipped and is not counted as a pass.

### Shop browser journeys and visual review

The release log confirms:
- **Buyer:** browse and open listing detail, save the listing, verify it in Saved, report with details, and contact the seller.
- **Seller:** open My Listings, inspect an owned listing, pause it, mark it sold, and reach the paid listing form with the KES 100/30-day disclosure.
- **Admin:** approve and reject listings, resolve a buyer report, and document payment review before allowing retry.

The Shop admin approval fixture uses a synthetic uploaded-photo object-key reference to exercise the moderation rule; it does not prove a real R2 upload. Paystack is mocked in the disposable PostgreSQL tests. Neither the browser fixture nor the mocked provider tests count as real Paystack/R2 provider verification.

The [16-image screenshot artifact 13856133486](https://github.com/apexstudying-cmd/prepza/actions/runs/43024634046/artifacts/13856133486) was downloaded and inspected. It includes Home and Shop at phone/tablet sizes, the listing editor, stale-cache states, buyer Saved/reported detail, seller listing detail and admin moderation. The pass confirms responsive composition, the Prepza navy/gold header and underline-tab hierarchy, familiar white-card surfaces, listing-card image proportions and fixed bottom navigation. It is not a student usability study or final visual sign-off.

### Current architecture snapshot and limits

On merged main 48a11afa5ca9b582d656cd83030f5dfefc87e22f:
- frontend/src/App.tsx: **5,034 lines**.
- app.py: **9,643 lines**.
- Admin: AdminSection.tsx 172 lines; useAdminSectionController.ts 934; AdminSectionCoreViews.tsx 783; AdminSectionPlatformViews.tsx 368; AdminGrowthPanels.tsx 531; AdminDomainPanels.tsx 728; AdminPanels.tsx remains a compatibility barrel.
- PodcastPlayerScreen.tsx: 349 lines, with offline cached-Blob replay retained.

The frontend architecture refactor is materially advanced but not complete. ChatDetail/Chats, DocumentStudy/Reader, generation flows, Home/Explore and app-shell orchestration remain high-coupling areas. Backend route/service/model decomposition remains open.

The overall release remains **BLOCKED**. The populated-database migration/backup-restore rehearsal must be repeated through Alembic head 20261030_shared_study_streak; Paystack sandbox and R2 object/header checks need safe staging credentials; document page-text migration/backfill and representative citation review remain open; Sentry delivery and request-ID propagation need verification; B2B viewability retains its client-observed 1.5-second limitation. No production deployment, live payment, purchase, new paid service, or billable GPU work was performed.

## 2026-11-12 — current-main post-merge verification and populated-database migration

The latest verified runtime code head is `0f393bd011d6047915cbb12a15acac87f21102c0`; current main is documentation-only commit `09bd1d82910d83797da2303a9f42afbd1739fbfe`. The repository had no open PRs at verification time.

- **Frontend Build:** [run 43171345722](https://github.com/apexstudying-cmd/prepza/actions/runs/43171345722) passed 124 source/transform tests, 5 offline Library tests, functional-wiring and ORM/schema audits, TypeScript, service-worker validation and production Vite build.
- **Release Browser/Cross-System Regression:** [run 43171345717](https://github.com/apexstudying-cmd/prepza/actions/runs/43171345717) passed on the exact current main SHA. The job built the production image, started disposable PostgreSQL/Redis, applied Alembic and controlled SQL-ledger migrations, started the app, passed phone-small (360x800), phone-standard (390x844) and tablet-portrait (768x1024), passed Shop buyer/seller/admin browser journeys and B2B browser-to-ledger checks, passed 99 disposable PostgreSQL QA tests (3536 warnings), passed online/offline Study Hub and generated-artifact journeys, uploaded screenshots (artifact [13922288483](https://github.com/apexstudying-cmd/prepza/actions/runs/43171345717/artifacts/13922288483)), and cleaned up disposable services.
- **Release QA Trace:** [run 43171345768](https://github.com/apexstudying-cmd/prepza/actions/runs/43171345768) passed all 11 feature traces with 0 failures and 0 warnings on the exact current main SHA. The previous trace attempt on 732760 failed because three manifest entries still looked for extracted study models in `app.py`; commit 0f393 updates `qa/release_manifest.json` to point at `study_models.py` and `document_models.py`, and the rerun is green.
- **Current push workflow inventory:** 13 observed push-triggered workflows on runtime head 0f393 completed successfully; after the documentation-only 09bd1d commit, all 12 push-triggered workflows completed successfully again. Conditional or PR-only workflows are not counted as passes.

### Populated-database migration and backup/restore

PostgreSQL Backup Restore Rehearsal [run 43171200015](https://github.com/apexstudying-cmd/prepza/actions/runs/43171200015) passed both jobs on code commit `73276018786bdaf007396c514fa0f358145138a7`:

1. **Existing database upgrade/data preservation:** created a representative prior-revision database at `20261005_chat_attach_source_doc`; seeded an existing document-content row and generated material before upgrade; upgraded to `20261030_shared_study_streak`; verified the document/material rows survived, `document_content.material_id` is nullable with its foreign key, Shop listing/saved/report tables and posting-payment review columns exist, and shared-streak tables exist.
2. **PostgreSQL custom dump/restore:** created a PostgreSQL 17 custom-format backup, restored it into a new disposable database, matched Alembic revision `20261030_shared_study_streak` and all 116 public tables, preserved the sentinel row, and connected the application to the restored database for a SQLAlchemy sentinel read. The disposable restore database and CI containers were cleaned up.

The migration/restore run is on 732760 and the full release-browser run is on 0f393. The only intervening commit updates the QA trace manifest to follow extracted model files, not application runtime behavior. Nevertheless, the strict final `clean_full_regression` gate remains **NOT_TESTED** until migration, backup/restore and the full release suite are rerun together on one exact SHA.

The Shop buyer/seller/admin journeys and responsive checks are now green on current main. The 16-image visual review artifact [13856133486](https://github.com/apexstudying-cmd/prepza/actions/runs/43024634046/artifacts/13856133486) remains the reviewed design reference. It confirms the compact underline tabs, navy/gold shell, white-card surfaces, 124px listing-image treatment and clearer price/title/meta hierarchy; it is not a student usability study. Real Paystack sandbox checkout/webhooks and real R2 object/header operations remain NOT_TESTED. The overall release remains BLOCKED; no production database, live payment, deployment, paid service or billable GPU operation was touched.

## 2026-11-13 — consolidated architecture candidate #79

- **Candidate:** `0c29859b3eb3b7acf3593e97eb9d08c57ac96acc`, PR [#79](https://github.com/apexstudying-cmd/prepza/pull/79), draft.
- **Frontend Build:** [43389767091](https://github.com/apexstudying-cmd/prepza/actions/runs/43389767091) PASS — 170 source/transform tests, 5 offline Library tests, functional/schema audits, TypeScript, service-worker checks and production Vite build.
- **Backend Shared Extension Contract:** [43389767160](https://github.com/apexstudying-cmd/prepza/actions/runs/43389767160) PASS — 45 tests and module compilation.
- **Other focused PR checks:** Admin Route [43389767044], Academic Catalog [43389767054], E2EE Chat [43389767040], E2EE Security [43389767197], Study Navigation [43389767037], Study Hub Runtime [43389767124], Student Frontend [43389767152], Student Contract [43389767043], B2B [43389767048], AI Economics [43389767174], AI Generation [43389767246], Prepza Control API [43389767310] and Kokoro Worker [43389767162] all PASS on the same candidate SHA. StudyHub Library Flow [43389767147] was SKIPPED by its path condition.
- **Release Browser/Cross-System Regression:** [43389767185](https://github.com/apexstudying-cmd/prepza/actions/runs/43389767185) PASS on exact SHA. Production image, disposable PostgreSQL/Redis, Alembic/SQL ledger, phone-small (360x800), phone-standard (390x844), tablet-portrait (768x1024), Shop buyer/seller/admin, B2B browser-to-ledger, 99 PostgreSQL QA tests, offline Study Hub lifecycle, multi-document generated-material replay, podcast descriptor/audio Blob replay and cleanup all passed. The 99-test suite emitted 3,536 warnings; warnings were not treated as failures.
- **Screenshots:** [artifact 14020905208](https://github.com/apexstudying-cmd/prepza/actions/runs/43389767185/artifacts/14020905208), 16 images. Key Shop browse, tablet browse, listing form, stale-cache, buyer, seller and admin screens were reviewed. The existing global Admin Platform floating control overlaps the bottom navigation on the admin screenshot.
- **Current main:** `64930add02dad22074500c3e6aa48ced19524e81` (documentation-only update); underlying code head `72f08742832dbc8a4b09469fadb72eea06ddf6da` had 11 observed push-triggered workflows all PASS.
- **Not same-SHA:** populated-database upgrade and PostgreSQL 17 backup/restore passed separately in [43171200015](https://github.com/apexstudying-cmd/prepza/actions/runs/43171200015) on `73276018786bdaf007396c514fa0f358145138a7`. The backup workflow does not currently trigger on application Python changes. `clean_full_regression` remains NOT_TESTED until that rehearsal runs on the same SHA.
- **Release disposition:** BLOCKED. Real Paystack/SES/OpenAI/R2/audio-GPU provider checks, page-text migration/backfill and citation review, external notification/request-ID delivery, B2B viewability, Home/PWA and same-SHA backup/restore remain open.

## 2026-11-14 — exact consolidated candidate verification

Candidate [PR #79](https://github.com/apexstudying-cmd/prepza/pull/79), exact head `edcfad751e4f3774e297219ecbb4c22cc31ef854`.

- **Frontend Build:** [43566535402](https://github.com/apexstudying-cmd/prepza/actions/runs/43566535402) PASS — 170 source/transform contracts, 5 offline Library tests, functional wiring audit, ORM/schema audit, TypeScript, service-worker validation and production Vite build.
- **Release Browser/Cross-System Regression:** [43566535290](https://github.com/apexstudying-cmd/prepza/actions/runs/43566535290) PASS on the same exact SHA — production image, disposable PostgreSQL/Redis, Alembic/controlled SQL ledger, 360x800/390x844/768x1024 responsive checks, Shop buyer/seller/admin, B2B browser-to-ledger, 99 disposable PostgreSQL tests (3,536 warnings), Study Hub online/offline lifecycle, multi-document generated-material replay, cached podcast descriptor/audio Blob, screenshot upload and disposable-service cleanup.
- **Shop role output:** seller E2EE public-key registration PASS; ChatDetail conversation load PASS; buyer browse/detail/save/report/contact and encrypted in-app message PASS; seller My Listings/pause/sold/paid listing form PASS; admin approve/reject/report resolution/payment review PASS. The Admin Platform floating-control clearance assertion passed after the shell offset change.
- **B2B browser-to-ledger:** PASS — offscreen and offline impressions generated no event/debit; fresh continuous visibility qualified; lost-response retry reused the same UUID; rapid-click and duplicate-click replay did not double-bill; raw clicks and unique/billable clicks reconciled in reports.
- **PostgreSQL Backup Restore Rehearsal:** [43566535421](https://github.com/apexstudying-cmd/prepza/actions/runs/43566535421) PASS on the same exact SHA — existing database upgraded from `20261005_chat_attach_source_doc` to `20261030_shared_study_streak` with seeded document/material preserved; Shop/streak schema verified; PostgreSQL 17 custom dump restored to a separate database with matching Alembic state/table count/sentinel; application health and database-backed universities smoke requests passed.
- **Other triggered workflows:** all 17 triggered workflows PASS on `edcfad751e4f3774e297219ecbb4c22cc31ef854`; StudyHub Library Flow [43566535404](https://github.com/apexstudying-cmd/prepza/actions/runs/43566535404) was SKIPPED by path conditions.
- **Screenshots:** [artifact 14102507070](https://github.com/apexstudying-cmd/prepza/actions/runs/43566535290/artifacts/14102507070), 17 images. Reviewed Home and Shop phone views, Shop tablet browse, buyer chat message, seller listing and admin moderation. The Admin Platform control now clears the five-item navigation.
- **Disposition:** `database_alembic`, `existing_database_migration`, `storage_backup_restore` and one-SHA `clean_full_regression` are PASS for this candidate. Shop remains IN_PROGRESS because real Paystack sandbox and R2 evidence is absent. Overall release remains BLOCKED by provider/staging, retrieval/citation, external monitoring, B2B viewability, Home/PWA and deployment gates. No production data or live provider was touched.


## 2026-11-14 — Upload/Choice/Processing extraction and exact-head release verification

- **Candidate:** PR [#79](https://github.com/apexstudying-cmd/prepza/pull/79), exact code head c494d147393035ac40bc8875f62d1ff6339c477a, still draft and unmerged.
- **Code boundary:** active UploadScreen, UploadShareChoiceScreen and ProcessingScreen moved to frontend/src/screens/upload/UploadFlowScreens.tsx. The app keeps route and active-document state and injects its existing TopBar. Shared getFileExtension/sha256Hex moved to frontend/src/lib/fileUtils.ts; file allow-list, 50 MiB document limit, 20 MiB chat attachment limit and image types moved to frontend/src/screens/upload/uploadConfig.ts. ChatDetail and ChatOptions still receive the same helper/limits.
- **Behavior-preservation contract:** file type/size checks, SHA-256, /me CSRF token, POST /documents, signed PUT, one 409-only confirmation retry after 1.5 seconds, duplicate-registration branch, local-first offline File persistence, private-by-default sharing choice, processing polling every 2.5 seconds, terminal states, timer cleanup, route IDs and AppShell no-nav policy are preserved. The moved screen bodies were not redesigned and no API behavior changed.
- **Frontend Build:** [43570716681](https://github.com/apexstudying-cmd/prepza/actions/runs/43570716681) PASS — 179 source/transform tests, 5 offline Library tests, functional wiring audit, ORM/schema audit, TypeScript, service-worker validation and production Vite build.
- **Release Browser/Cross-System Regression:** [43570716679](https://github.com/apexstudying-cmd/prepza/actions/runs/43570716679) PASS on the same SHA — production image, disposable PostgreSQL/Redis, Alembic/SQL ledger, phone-small (360x800), phone-standard (390x844), tablet-portrait (768x1024), Shop buyer/seller/admin, B2B browser-to-ledger, 99 PostgreSQL QA tests (3,536 warnings), online/offline Study Hub, generated-artifact replay and screenshot upload. Offline artifact replay explicitly made no generation POST requests.
- **PostgreSQL Backup Restore Rehearsal:** [43570716644](https://github.com/apexstudying-cmd/prepza/actions/runs/43570716644) PASS on the same SHA — existing-database migration/data preservation and PostgreSQL 17 custom-format backup/restore both passed; restored-data application smoke tests passed.
- **Other triggered workflows:** all 17 triggered workflows PASS on c494d147393035ac40bc8875f62d1ff6339c477a; StudyHub Library Flow [43570716663](https://github.com/apexstudying-cmd/prepza/actions/runs/43570716663) was SKIPPED by path condition.
- **Screenshot artifact:** [14103724866](https://github.com/apexstudying-cmd/prepza/actions/runs/43570716679/artifacts/14103724866), 17 responsive images captured. Shop source is unchanged from the previous reviewed Shop visual artifact [14102507070](https://github.com/apexstudying-cmd/prepza/actions/runs/43566535290/artifacts/14102507070).
- **Initial contract mismatch:** Frontend Build [43570635198](https://github.com/apexstudying-cmd/prepza/actions/runs/43570635198) failed on intermediate head ac06cbd29ba04a27ced5932a842ef1cf620f07cd because the Morio identity test still counted the Processing screen's /icon-192.png from App.tsx. The test was retargeted to UploadFlowScreens and retained its original minimum-count assertion; final Frontend Build passed without weakening tests.
- **Disposition:** database_alembic, existing_database_migration, storage_backup_restore, mobile_responsive_visual, cross_system_journeys, ci_release_workflows and one-SHA clean_full_regression are PASS on this candidate. Shop remains IN_PROGRESS pending real Paystack sandbox and R2 evidence. Overall release remains BLOCKED by provider/staging, retrieval/citation, external monitoring, B2B viewability, remaining architecture and deployment gates. No production data, live payment, deployment, paid service or billable GPU operation was touched.


## 2026-11-14 — PublishLibrary module extraction (PR #79)

The active PublishLibrary screen was moved from App.tsx to frontend/src/screens/library/PublishLibraryScreen.tsx. App.tsx retains the existing route and active-document state and injects EmptyState. The original screen body, publish API request, ready-document eligibility, rights confirmation, CSRF header, payload fields and navigation destinations were preserved.

The module-aware transform in tools/apply_library_publish_context_ux.py now applies to the extracted screen and is idempotent. A new temporary-tree test executes the transform twice and checks the second run is a no-op. The upload/publish verifier follows the extracted UploadFlowScreens and PublishLibraryScreen modules and checks the shared navigation type.

- **Candidate:** PR #79 head 8a78cd0e6ae87e8a08c3739b5aca50f9dbe493fd (draft; not merged).
- **Frontend Build:** [43583027683](https://github.com/apexstudying-cmd/prepza/actions/runs/43583027683) PASS. The source/module/transform suite passed 180 tests; the offline Library regression passed 5 tests; upload/publish module ownership verification, functional-wiring audit, ORM/schema drift audit, TypeScript, service-worker validation and production Vite build all passed. The build log confirms the Library publish academic-context transform executed against the module.
- **Full Release Browser:** [43583027599](https://github.com/apexstudying-cmd/prepza/actions/runs/43583027599) PASS on application-code head 8a78cd0e6ae87e8a08c3739b5aca50f9dbe493fd: production image, disposable PostgreSQL/Redis and migrations, responsive phone/tablet, Shop buyer/seller/admin journeys, B2B browser-to-ledger, 99 disposable PostgreSQL tests, online/offline Study Hub and generated-artifact/podcast Blob replay, screenshots and cleanup. This is broad cross-system evidence, not a dedicated PublishLibrary usability study or live provider verification. PostgreSQL Backup Restore Rehearsal [43583027733](https://github.com/apexstudying-cmd/prepza/actions/runs/43583027733) also PASS on the same exact application-code head: existing-database upgrade/data preservation and PostgreSQL custom-format dump/restore both succeeded. All 17 triggered workflows passed; StudyHub Library Flow [43583027630](https://github.com/apexstudying-cmd/prepza/actions/runs/43583027630) was skipped by path condition.
- **Source sizes:** App.tsx 2,552 lines; PublishLibraryScreen.tsx 241 lines; app.py 8,791 lines.
- **Intermediate test corrections:** initial runs exposed stale assertions that expected the moved component/helper imports in App.tsx and an upload verifier that expected the Screen union to remain inline. Tests now assert module ownership and the shared navigation type; no implementation behavior assertion was removed.

No production database, deployment, live payment, new paid service or billable GPU operation was performed. Overall release remains BLOCKED by provider, retrieval/citation, monitoring, B2B viewability, Home/PWA and deployment gates.


## 2026-11-14 — Subscription/Payment characterization suite

The initial characterization suite for the existing inline SubscriptionScreen, PaymentScreen, PaymentSuccessScreen, PaymentFailureScreen and PaymentHistoryScreen passed before extraction. Frontend Build [43583651298](https://github.com/apexstudying-cmd/prepza/actions/runs/43583651298) on test/workflow head 7f9b2072472710c2d794b090e88a3647609e4809 passed 185 source/module/transform tests and five offline Library tests, then TypeScript, production Vite build, service-worker and architecture audits. This protects lifted selectedPlan state, plan/status/usage API reads, CSRF checkout request/payload, Paystack redirect_url navigation, duplicate-submit guard, payment-history statuses, pending/failure distinction and success timer cleanup. No billing implementation moved and no payment request was made.


## 15 November 2026 — latest verified candidate before ambassador route extraction

Exact code head: `b24d583f054f056161c714a15d558406672acb4d` on PR #79.

- **Frontend Build:** [43686512095](https://github.com/apexstudying-cmd/prepza/actions/runs/43686512095) PASS — source/transform contracts, offline Library regression, functional-wiring audit, ORM/schema audit, TypeScript, service-worker validation and production Vite build.
- **Release Browser and Cross-System Regression:** [43686511971](https://github.com/apexstudying-cmd/prepza/actions/runs/43686511971) PASS — the responsive/cross-system release job completed successfully on this code head.
- **PostgreSQL Backup Restore Rehearsal:** [43686511937](https://github.com/apexstudying-cmd/prepza/actions/runs/43686511937) PASS — both the existing-database upgrade/data-preservation job and the PostgreSQL custom dump/restore job succeeded.
- **Workflow inventory:** 17 triggered workflows succeeded. StudyHub Library Flow [43686511919](https://github.com/apexstudying-cmd/prepza/actions/runs/43686511919) was SKIPPED by its path condition and is not counted as a pass.
- **Source snapshot:** App.tsx 2,130 lines; app.py 6,328; PublishLibraryScreen 241; SubscriptionScreens 415; AdminSection 172; useAdminSectionController 934.
- **Disposition:** this is a verified code candidate, not a launch approval. Shop automated role journeys and responsive checks are covered by Release Browser, but real Paystack/R2 evidence remains NOT_TESTED. B2B browser metering passes its current contract, but server-side proof of the client dwell condition remains unresolved.

## 15 November 2026 — ambassador route extraction (verification pending)

The student ambassador endpoints are being moved into `ambassador_routes.py` through the existing route registry. The existing settings/tier/referral-code helpers remain in `app.py` for shared referral lifecycle hooks. Route registration order, endpoint names, methods, CSRF and rate-limit decorators are preserved. The existing real-DB payout-bundle regression remains in `tests/test_local_qa_real_world.py`; new route-registry contracts cover all seven endpoint mappings and guard placement. **NOT_TESTED** until the workflows triggered by the new code head complete.


## Pull-request verification — 2026-11-16 (Create menu screen extraction, PR #79)

Code commit `38e656e6670bbafcc5f22233210c8f3183e22269` extracts the active `CreateModal` route from `frontend/src/App.tsx` into `frontend/src/screens/create/CreateModalScreen.tsx`. The existing 32-line component body was compared against the previous App.tsx implementation and is byte-equivalent after normalizing only `export default`; the existing route ID and route dispatch remain unchanged. The four existing menu entries, icons, descriptions, CORE badge, theme tokens, styling, close-to-Home action and destination routes are covered by two new regression tests. No visual redesign or navigation item was added.

The extraction also removed App.tsx's now-unused Pill import. A pre-existing Settings ownership assertion had incorrectly required that import to remain in App.tsx even though `SettingsScreen.tsx` imports and owns Pill directly. The assertion now checks the actual Settings module dependency instead of preserving a stale file-location assumption.

- **Frontend Build:** [run 43819731996](https://github.com/apexstudying-cmd/prepza/actions/runs/43819731996) PASS on exact SHA `38e656e6670bbafcc5f22233210c8f3183e22269`: 190 frontend source/transform/module contracts passed; 5 offline Library tests passed; functional-wiring and ORM/schema audits, TypeScript, service-worker validation and production Vite build passed.
- **PostgreSQL Backup Restore Rehearsal:** [run 43819732082](https://github.com/apexstudying-cmd/prepza/actions/runs/43819732082) PASS on the same SHA. Existing-database upgrade/data preservation and PostgreSQL custom-format dump/restore both passed, including restored-data application smoke testing.
- **Study Hub Runtime Regression:** [run 43819732154](https://github.com/apexstudying-cmd/prepza/actions/runs/43819732154) PASS.
- **Release Browser/Cross-System Regression:** [run 43819732136](https://github.com/apexstudying-cmd/prepza/actions/runs/43819732136) PASS on exact SHA `38e656e6670bbafcc5f22233210c8f3183e22269`. The production image, disposable PostgreSQL/Redis, Alembic/SQL ledger, phone/tablet responsive checks, Shop buyer/seller/admin journeys, B2B browser-to-ledger regression, full disposable PostgreSQL QA (**100 passed, 0 failed, 3,549 warnings**), online/offline Study Hub lifecycle, generated-artifact replay, screenshot upload and cleanup all passed. The offline journey verified podcast audio Blob replay, multiple documents surviving reload, Summary/Flashcards/Practice Questions/Mind Maps reopening offline, and zero generation POSTs during replay. Screenshot artifact [14204415875](https://github.com/apexstudying-cmd/prepza/actions/runs/43819732136/artifacts/14204415875) contains 17 images.
- **Other triggered workflows:** all 17 triggered workflows succeeded on the exact code SHA. StudyHub Library Flow [run 43819732065](https://github.com/apexstudying-cmd/prepza/actions/runs/43819732065) was skipped by path condition and is not counted as a pass.

PR #79 remains open and draft. The previous exact candidate `76c5508514e9fdd4e396c600a5566dc4ff07a257` separately passed full Release Browser [43817434101](https://github.com/apexstudying-cmd/prepza/actions/runs/43817434101) and PostgreSQL Backup Restore [43817434005](https://github.com/apexstudying-cmd/prepza/actions/runs/43817434005), but that adjacent-SHA evidence is not substituted for the pending full regression on `38e656e`. Overall release remains BLOCKED by provider, retrieval/citation, monitoring, B2B viewability and deployment gates. No live provider, production data, paid service, deployment or billable GPU operation was used.


## 2026-11-16 — Remaining inline route ownership audit

After the exact-head CreateModal extraction and full regression pass, I scanned the current App.tsx route switch against its component declarations and navigation call sites. The only remaining inline component rendered by the route switch is `EduUploadForm` (34 lines). It is still present in the `Screen` union, route dispatch and BottomNav home grouping. No current code calls `setScreen('edu-upload-form')`, but `useAppNavigation` restores its `screenStack` from sessionStorage, so a previously persisted stack can still reopen this route. Preserve it and extract it with the existing `TopBar` injected as a typed prop; do not remove the route or change its form UI. `DocumentStudyScreen` remains an unmounted legacy declaration: the `document-study` route dispatches to `DocumentStudyHubScreen`, so it is not extracted as part of this pass.


## 17 November 2026 — persisted education-upload route extraction (PR #79)

Code head: `4a5cfc10b4e20e308436f5f64f9bbf235be0f243`.

The compatibility-reachable `EduUploadForm` screen moved from `frontend/src/App.tsx` to `frontend/src/screens/upload/EduUploadFormScreen.tsx`. Its existing component body (local content-type state, six choices, three fields, layout, inline styling, injected TopBar/back action and Upload destination) compares byte-for-byte after ignoring only trailing blank lines. App retains the route ID and dispatch; the Screen union, BottomNav Home grouping and sessionStorage-restored navigation stack remain unchanged. No UI redesign, new navigation item, Home Quick Action, API call or business rule was introduced. App.tsx is now 2,066 lines.

The first implementation candidate `4ed0420c1a8067009d2d2f8a636f82a99d92f486` exposed two defects: an import insertion shifted the offsets used to remove the old component, leaving part of its JSX in App.tsx; and the new test treated the already-loaded `NAVIGATION` source string as a Path. TypeScript and the source-contract test failed on that candidate. Both defects were corrected in `4a5cfc10b4e20e308436f5f64f9bbf235be0f243`; no failing test was removed, weakened or skipped.

- **Frontend Build:** [run 44031976544](https://github.com/apexstudying-cmd/prepza/actions/runs/44031976544) PASS on exact SHA `4a5cfc10b4e20e308436f5f64f9bbf235be0f243`: 192 frontend source/transform/module tests passed; 5 offline Library tests passed; functional-wiring and ORM/schema audits, TypeScript, service-worker validation and production Vite build passed.
- **Release Browser and Cross-System Regression:** [run 44031976661](https://github.com/apexstudying-cmd/prepza/actions/runs/44031976661) PASS on the same SHA: production image, disposable PostgreSQL/Redis, Alembic migrations and SQL ledger; phone-small (360x800), phone-standard (390x844) and tablet-portrait (768x1024); Shop buyer/seller/admin journeys; B2B browser-to-ledger; **100 PostgreSQL QA tests passed / 0 failed / 3,549 warnings**; online/offline Study Hub lifecycle and generated-artifact replay; screenshot upload and disposable-service cleanup. Offline replay confirmed multiple documents and all four generated material types survive reload and reopen offline, cached podcast audio Blob playback works, and replay makes no generation POST requests. Screenshot artifact [14305199157](https://github.com/apexstudying-cmd/prepza/actions/runs/44031976661/artifacts/14305199157).
- **PostgreSQL Backup Restore Rehearsal:** [run 44031976660](https://github.com/apexstudying-cmd/prepza/actions/runs/44031976660) PASS on the same SHA: existing-database upgrade/data preservation and PostgreSQL custom-format dump/restore, including restored-data application smoke test.
- **Other workflow inventory:** 17 triggered workflows succeeded on this exact SHA. StudyHub Library Flow [run 44031976586](https://github.com/apexstudying-cmd/prepza/actions/runs/44031976586) was SKIPPED by path condition and is not counted as a pass.

The exact-head candidate has no remaining active inline screen component in the App route switch. The unmounted legacy `DocumentStudyScreen` remains untouched. Backend route decomposition is not complete: payment history, Paystack callback/webhook and student subscription plans/status/upgrade routes still need dependency/contract mapping. Overall release remains **BLOCKED** by provider verification, retrieval/citation review, external monitoring/request-ID delivery, independently verified B2B viewability, Home/PWA sign-off and deployment authorization. No live provider, production data, paid infrastructure, deployment or billable GPU work was used.


## 2026-11-17 — student subscription route extraction (PR #79)

**Application-code commit:** `f42d447ddde2c5c72100884f83c2358c6e163535`.

Moved only the three student subscription route handlers from `app.py` into `student_subscription_routes.py`, registered through `route_registry.py` at the former subscription route location. Existing route names, paths, methods and registration order are preserved. The module receives the current User/Payment models, DB, limiter, client-address helper, CSRF guard, subscription-status helper, Paystack initializer and student-order helper mapping as explicit dependencies.

New `tests/test_student_subscription_routes_contract.py` covers exact GET/POST route map, rate-limit and CSRF decoration, admin-configured plan response fields, unauthenticated status/upgrade behavior, status payload, pending-checkout recovery (no second provider initialization), successful mocked checkout/payment/order snapshot, and invalid/unavailable/unconfigured plan responses. `tests/test_backend_route_registry_contract.py` protects the app registration point and dependency forwarding. Backend CI compiles the new module and runs both suites.

- **Backend Shared Extension Contract:** [run 44035476830](https://github.com/apexstudying-cmd/prepza/actions/runs/44035476830) PASS.
- **Frontend Build:** [run 44035476389](https://github.com/apexstudying-cmd/prepza/actions/runs/44035476389) PASS, including launch-wiring/schema audits, TypeScript and production build.
- **PostgreSQL Backup Restore Rehearsal:** [run 44035476520](https://github.com/apexstudying-cmd/prepza/actions/runs/44035476520) PASS; existing database upgrade/data preservation and custom-format restore jobs both passed.
- **Release Browser/Cross-System Regression:** [run 44035476605](https://github.com/apexstudying-cmd/prepza/actions/runs/44035476605) IN_PROGRESS at the time of this record. Full responsive, Shop, B2B, PostgreSQL QA and offline-artifact results on this exact SHA are not claimed until it completes.
- **Workflow inventory:** 16 succeeded, 1 in progress, 1 skipped by path condition.

The extraction did not move or modify `student_subscription_billing.py`, `sync_paystack_payment_status`, Paystack callback/webhook handling, payment history, the subscription plan configuration service, or any UI. No provider request or payment was initiated. Overall release remains BLOCKED.

## 17 November 2026 — exact-head subscription candidate regression completed

The exact PR #79 head `33024391a7f230704cc74ce338905e13159db313` has completed its previously pending full verification:
- Release Browser/Cross-System Regression [44035945337](https://github.com/apexstudying-cmd/prepza/actions/runs/44035945337): PASS.
- Frontend Build [44035945354](https://github.com/apexstudying-cmd/prepza/actions/runs/44035945354): PASS.
- Backend Shared Extension Contract [44035945449](https://github.com/apexstudying-cmd/prepza/actions/runs/44035945449): PASS.
- PostgreSQL Backup Restore [44035945370](https://github.com/apexstudying-cmd/prepza/actions/runs/44035945370): PASS, both existing-database upgrade/data preservation and custom-format restore jobs.
- Workflow inventory: 17 triggered workflows succeeded; StudyHub Library Flow [44035945281](https://github.com/apexstudying-cmd/prepza/actions/runs/44035945281) was SKIPPED by path condition and is not counted as a pass.

This closes the pending automated migration, responsive/cross-system regression and exact-head CI evidence for the student-subscription route extraction. It does not close live-provider verification, retrieval/index/citation review, external monitoring/request-ID, independent B2B viewability, human Home/PWA sign-off or deployment authorization. Overall release remains BLOCKED; PR #79 remains draft and unmerged.

## 18 November 2026 — payment-history route boundary verified

The latest behavior-preserving backend slice is code commit 5cd6338a8435233d0480a1b6449a102f4786cdcc. The existing GET /payment-history handler moved from app.py into student_payment_history_routes.py; app.py delegates through route_registry.py at the original route position. The endpoint name, GET method, manual session authentication/401, user filter, subscription/add-on filter, descending creation-time order, response fields and legacy-content exclusion are unchanged. The new contract covers route/method, anonymous access, user/type filtering, ordering and response payload; the registry test protects explicit dependency forwarding and registration placement. The launch-wiring audit and backend workflow now include the module.

**Exact code-head evidence**
- Backend Shared Extension Contract [44255257558](https://github.com/apexstudying-cmd/prepza/actions/runs/44255257558): PASS, 94 tests passed.
- Frontend Build [44255257473](https://github.com/apexstudying-cmd/prepza/actions/runs/44255257473): PASS, 192 source/module tests + 5 offline Library tests; TypeScript, production Vite build and launch-wiring/audits passed.
- Release Browser/Cross-System Regression [44255257490](https://github.com/apexstudying-cmd/prepza/actions/runs/44255257490): PASS, 100 PostgreSQL QA tests (0 failed; 3,549 warnings), responsive phone/tablet, Shop buyer/seller/admin journeys, B2B browser-to-ledger, Study Hub offline lifecycle and generated-artifact replay.
- PostgreSQL Backup Restore [44255257455](https://github.com/apexstudying-cmd/prepza/actions/runs/44255257455): PASS; existing-database upgrade/data preservation and custom-format backup/restore jobs passed.
- Workflow inventory: 17 triggered workflows succeeded; StudyHub Library Flow [44255257439](https://github.com/apexstudying-cmd/prepza/actions/runs/44255257439) was SKIPPED by path condition and is not counted as a pass.
- Responsive screenshots: [artifact 14405628563](https://github.com/apexstudying-cmd/prepza/actions/runs/44255257490/artifacts/14405628563).

No provider calls, payment, UI, styling, navigation, database/production-data changes or deployment occurred. This is automated regression evidence, not live-provider or production certification.

**Next architecture boundary:** characterize the shared Paystack callback/webhook before moving it: HMAC signature rejection, authoritative transaction verification, retry/duplicate delivery, charge/subscription/refund dispatch and ambassador-transfer reconciliation. Keep the lifecycle service and registration order intact.

## 2026-11-19 — subscription billing registration repair and exact-head regression

Candidate code head: `e094830e323e9993c2b2dbef6844f9105a4b5523` on the existing PR #79 branch.

Source-history inspection found that `student_subscription_billing.py` had been truncated: `register_student_subscription_billing` ended inside the refund-quote route and returned no handler map. This left `_student_subscription_billing` as `None` at app registration and removed the original refund-request, cancellation and admin-refund route registrations. The missing tail was restored from historical commit `a86b1fc90c1d73b57e345100c13e11250e66d6fa`, retaining the current module's later schema-ownership and race-safe-upsert changes. No payment/refund API was called.

Added `test_student_subscription_billing_registration_and_webhook_dispatch_contract` to `tests/test_local_qa_real_world.py`. It protects the returned handler map, restored route map, missing-secret 503, `subscription.create`, subscription lifecycle events, all five refund event dispatches, recurring-charge fallback and unknown-event acknowledgement. **This new regression test is NOT_TESTED on this candidate**, because Release Browser failed before the full PostgreSQL QA step.

- Frontend Build [44472584288](https://github.com/apexstudying-cmd/prepza/actions/runs/44472584288): PASS.
- Backend Shared Extension Contract [44472584299](https://github.com/apexstudying-cmd/prepza/actions/runs/44472584299): PASS.
- Student Contract Validation [44472584308](https://github.com/apexstudying-cmd/prepza/actions/runs/44472584308): PASS.
- Admin Route Contract [44472584408](https://github.com/apexstudying-cmd/prepza/actions/runs/44472584408): PASS.
- PostgreSQL Backup Restore [44472584319](https://github.com/apexstudying-cmd/prepza/actions/runs/44472584319): PASS.
- Release Browser [44472584583](https://github.com/apexstudying-cmd/prepza/actions/runs/44472584583): FAIL at `scripts/test_browser_shop_journeys.py`; responsive phone/tablet checks passed, but the buyer's POST to `/chats/<id>/messages` returned 403 `Missing or invalid CSRF token`. B2B, full PostgreSQL QA and offline/generated-artifact journeys were SKIPPED.
- Workflow inventory: 16 succeeded, 1 failed, 1 skipped (StudyHub Library Flow [44472584302](https://github.com/apexstudying-cmd/prepza/actions/runs/44472584302)).

Do not count the new billing regression as PASS until it executes on an exact passing head. No UI styling/navigation, KES 100/30-day listing rule, production data, live provider, payment, payout, deployment, paid service or billable GPU work changed.

## 2026-11-19 — subscription refund-request route repair and exact-head regression (PR #79)

On exact code head `7d12cbfebbc2bf48f501cb25ad2f3d979aae4631`, the existing refund request body had been placed inside GET `/subscription/refund-quote`. This both made the GET handler mutate refund state and left POST `/subscription/refund-request` unregistered. The previous exact-head Release Browser run [44474023200](https://github.com/apexstudying-cmd/prepza/actions/runs/44474023200) passed Shop buyer/seller/admin and B2B journeys, then exposed the missing refund-request route in full PostgreSQL QA. The earlier Shop 403 on candidate `e094830` did not reproduce on the later browser runs.

Commit [7d12cbf](https://github.com/apexstudying-cmd/prepza/commit/7d12cbfebbc2bf48f501cb25ad2f3d979aae4631) restores the original API split: GET quote is read-only and returns the quote; POST request is separately registered with the existing CSRF guard, authenticated session, payment/plan validation, duplicate-request check, upsert and 201 response. Added `tests/test_student_subscription_billing_contract.py` covers route methods, read-only GET, 401, CSRF rejection, persisted fields and duplicate 409. No payment provider call was made and no frontend/UI file changed.

- Backend Shared Extension Contract [44475284636](https://github.com/apexstudying-cmd/prepza/actions/runs/44475284636): PASS, 96 tests.
- Frontend Build [44475284756](https://github.com/apexstudying-cmd/prepza/actions/runs/44475284756): PASS, 192 source/module + 5 offline Library tests, TypeScript and production build; AdminSection boundary tests included.
- Release Browser [44475284585](https://github.com/apexstudying-cmd/prepza/actions/runs/44475284585): PASS; responsive phone/tablet, Shop buyer/seller/admin journeys, B2B browser-to-ledger, **101 PostgreSQL QA tests**, Study Hub offline lifecycle, generated materials and podcast audio replay.
- PostgreSQL Backup Restore [44475284651](https://github.com/apexstudying-cmd/prepza/actions/runs/44475284651): PASS; existing database upgrade/data preservation and custom-format backup/restore both passed.
- AI Economics [44475284794](https://github.com/apexstudying-cmd/prepza/actions/runs/44475284794): 81 passed; E2EE Security [44475284746](https://github.com/apexstudying-cmd/prepza/actions/runs/44475284746): 16 passed.
- 17 triggered workflows succeeded; StudyHub Library Flow [44475284566](https://github.com/apexstudying-cmd/prepza/actions/runs/44475284566) was skipped by path condition.
- Responsive screenshot artifact: [14506038883](https://github.com/apexstudying-cmd/prepza/actions/runs/44475284585/artifacts/14506038883).

The earlier Shop CSRF failure did not recur in the later exact-head Shop browser journeys. Automated Shop flows now pass, but Paystack sandbox and R2 provider operations remain NOT_TESTED. B2B browser-to-ledger passes, but independent server-side verification of the 50%-visible/1.5-second dwell condition remains open. Architecture refactor remains incomplete: characterize the shared Paystack callback/webhook and recover the missing ambassador-transfer helper contract before moving that boundary. Retrieval/index/citation review, external monitoring/request-ID delivery, Home/PWA sign-off and deployment authorization remain open. Release remains **BLOCKED**; PR #79 remains draft/unmerged.


## 2026-11-19 — ambassador transfer call-boundary characterization

Code/test commit [19a4c73](https://github.com/apexstudying-cmd/prepza/commit/19a4c7376bfa775b42c109ab3444683b3f0f1615) adds `test_ambassador_transfer_routes_delegate_to_mocked_provider_boundary` to `tests/test_local_qa_real_world.py` and records it in `qa/release_manifest.json`.

The test uses only injected mocks in the disposable PostgreSQL environment. It verifies:
- Admin payout approval delegates to `initiate_paystack_transfer(payout)` and records the returned transfer reference.
- Admin status synchronization delegates to `sync_paystack_transfer_status(payout)`.
- Signed `transfer.success`, `transfer.failed` and `transfer.reversed` webhooks dispatch the corresponding status to `_apply_paystack_transfer_result(payout, status)`.
- The fake apply handler is state-neutral; no paid/rejected/pending transition is asserted or invented.

Historical inspection: `admin_reconciled_ambassadors.py` first appeared in [54108e7](https://github.com/apexstudying-cmd/prepza/commit/54108e732958c2907dab28b97082d9ba0717965c). Its parent `a478144028dac084fd21d6fbdb047be29f7702f2` already contained the webhook reference but no helper definitions; the current source tree also contains only call sites. Model comments specify a reusable Paystack recipient code and transfer-reference lookup, but not failure/reversal money-state behavior. Therefore the mock test protects the integration seam only; it does not make transfers operational.

Exact-head CI on `19a4c7376bfa775b42c109ab3444683b3f0f1615`:
- Backend Shared Extension Contract [44479377130](https://github.com/apexstudying-cmd/prepza/actions/runs/44479377130): PASS, 96 tests.
- Frontend Build [44479377187](https://github.com/apexstudying-cmd/prepza/actions/runs/44479377187): PASS, 192 source/module tests + 5 offline Library tests, TypeScript and production Vite build.
- Release Browser [44479377175](https://github.com/apexstudying-cmd/prepza/actions/runs/44479377175): PASS, **102 PostgreSQL QA tests, 0 failures**; responsive phone/tablet, Shop buyer/seller/admin, B2B browser-to-ledger, Study Hub offline and generated-material/podcast replay all passed.
- PostgreSQL Backup Restore [44479377074](https://github.com/apexstudying-cmd/prepza/actions/runs/44479377074): PASS, existing-database upgrade/data preservation and custom-format restore.
- Workflow inventory: 17 triggered workflows succeeded; StudyHub Library Flow [44479377186](https://github.com/apexstudying-cmd/prepza/actions/runs/44479377186) was SKIPPED by path condition.

Disposition: mocked route/webhook delegation test PASS; actual transfer recipient creation, transfer API call, verification, retry/deduplication and success/failure/reversal state transitions remain NOT_TESTED. No provider credentials were used and no live transfer occurred.


## 2026-11-20 — administrative audit-log route extraction and exact-head regression (PR #79)

The existing GET `/admin/audit-logs` handler moved from `app.py` into `admin_audit_routes.py`. `route_registry.py` forwards the existing database, `AuditLog` and `User` models plus the same `require_admin` guard. The registry call remains at the original point after `log_admin_action` and before `register_control_feature_routes`. The route keeps its GET method and endpoint name, 30-day default and 1–365-day clamp, actor/action/target filters, newest-first ordering, 50-row pagination, actor email, JSON-or-string details parsing and response shape.

The new Flask/SQLite contract covers the exact route map and authorization outcomes (anonymous 401; ordinary and suspended admin 403; persisted admin allowed), query filters, descending order, page boundaries and serialized details. The route-registry contract verifies explicit dependency forwarding and original registration order. The backend workflow compiles the new route module and executes the new tests on PR and main-push paths.

An initial test run on intermediate commit `8edc15c` failed because the test fixture gave two entries equal timestamps and expected deterministic tie ordering. That was a fixture defect, not a production route failure. The fixture now uses distinct timestamps; the production `ORDER BY created_at DESC` behavior was preserved without adding an unrequested tie-breaker.

**Exact application-code head:** [a5d17da6478333803966f263669db44d156d9c82](https://github.com/apexstudying-cmd/prepza/commit/a5d17da6478333803966f263669db44d156d9c82)

- Backend Shared Extension Contract [44686577859](https://github.com/apexstudying-cmd/prepza/actions/runs/44686577859): PASS — **100 passed, 6 warnings**; new route and registry contracts included.
- Frontend Build [44686577881](https://github.com/apexstudying-cmd/prepza/actions/runs/44686577881): PASS — **192 source/module + 5 offline Library tests**; TypeScript, production Vite build, launch-wiring and architecture audits passed.
- Release Browser/Cross-System Regression [44686577870](https://github.com/apexstudying-cmd/prepza/actions/runs/44686577870): PASS — **102 PostgreSQL QA tests, 0 failures, 3,557 warnings**; production image, disposable PostgreSQL/Redis, Alembic and controlled migration ledger, phone/tablet responsive checks, Shop buyer/seller/admin browser journeys, B2B browser-to-ledger, Study Hub offline lifecycle and generated-material/podcast offline replay passed. Responsive screenshot artifact: [14606388788](https://github.com/apexstudying-cmd/prepza/actions/runs/44686577870/artifacts/14606388788).
- PostgreSQL Backup Restore Rehearsal [44686577998](https://github.com/apexstudying-cmd/prepza/actions/runs/44686577998): PASS — both existing-database upgrade/data preservation and custom-format backup/restore jobs passed.
- Workflow inventory: **17 triggered workflows succeeded;** StudyHub Library Flow [44686577858](https://github.com/apexstudying-cmd/prepza/actions/runs/44686577858) was SKIPPED by path condition and is not counted as a pass.

No UI, navigation, API payload, authorization rule, database schema, Shop business rule, payment behavior, provider call, production data or deployment changed. The new route boundary is PASS. The broader architecture refactor remains incomplete; ambassador transfers and external providers remain NOT_TESTED, and release remains BLOCKED.


## 20 November 2026 — Library screen module-ownership test correction and exact-head regression

Main's latest commit `7922fa0d27fb275382e9fa4f46bfe4f242acdcf3` was a test-only correction: the Library material helper import is owned by `LibraryScreen.tsx`, not `App.tsx`. The PR #79 branch was one commit behind main, so the same assertion was applied to `tests/test_library_screen_module_contract.py` in code commit [`a48aefc`](https://github.com/apexstudying-cmd/prepza/commit/a48aefc81fa9f3f58d1d0ba9e7a3dbd04285c00e). It now checks `from '../../lib/library'` in the screen module. No production source, UI, API, navigation, styling or runtime behavior changed.

Exact application-code/test head `a48aefc81fa9f3f58d1d0ba9e7a3dbd04285c00e`:
- Backend Shared Extension Contract [44688623735](https://github.com/apexstudying-cmd/prepza/actions/runs/44688623735): PASS — 100 tests, 6 warnings.
- Frontend Build [44688623559](https://github.com/apexstudying-cmd/prepza/actions/runs/44688623559): PASS — 192 source/module tests and 5 offline Library tests; TypeScript, production Vite build, screen/offline/calling audits and launch-wiring audit passed.
- Release Browser/Cross-System Regression [44688623523](https://github.com/apexstudying-cmd/prepza/actions/runs/44688623523): PASS — 102 PostgreSQL QA tests, 0 failures; production image, disposable PostgreSQL/Redis, Alembic and controlled migration ledger, phone/tablet responsive checks, Shop buyer/seller/admin journeys, B2B browser-to-ledger, Study Hub offline lifecycle, 12 generated-material replays and podcast audio Blob replay passed. The suite emitted 3,557 warnings, primarily existing deprecations. Screenshot artifact [14607827213](https://github.com/apexstudying-cmd/prepza/actions/runs/44688623523/artifacts/14607827213).
- PostgreSQL Backup Restore Rehearsal [44688623724](https://github.com/apexstudying-cmd/prepza/actions/runs/44688623724): PASS — existing-database upgrade/data preservation and PostgreSQL 17 custom-format backup/restore.
- Admin Route Contract [44688623534](https://github.com/apexstudying-cmd/prepza/actions/runs/44688623534), Study Hub Runtime [44688623671](https://github.com/apexstudying-cmd/prepza/actions/runs/44688623671), E2EE Chat [44688623554](https://github.com/apexstudying-cmd/prepza/actions/runs/44688623554), B2B contract [44688623637](https://github.com/apexstudying-cmd/prepza/actions/runs/44688623637), and the remaining triggered workflows: PASS.
- Workflow inventory: 17 triggered workflows succeeded; StudyHub Library Flow [44688623679](https://github.com/apexstudying-cmd/prepza/actions/runs/44688623679) was SKIPPED by path condition and is not counted as a pass.

Disposition: Library module-ownership assertion PASS; frontend TypeScript/production build PASS; backend contract PASS; full responsive, Shop, B2B, PostgreSQL, Study Hub and artifact regression PASS. StudyHub Library Flow was SKIPPED by its path condition. Existing Shop provider operations (Paystack sandbox and R2 object/header verification) remain NOT_TESTED; Shop remains IN_PROGRESS and release remains BLOCKED.

## 21 November 2026 — Paystack browser callback characterization and exact-head regression (PR #79)

The existing browser return route is now characterized before any extraction. `test_paystack_browser_callback_prefers_reference_then_trxref_and_fails_closed` verifies `reference` precedence, `trxref` fallback, the existing SPA success redirect, missing-reference error redirect, and provider-sync exception handling. `qa/release_manifest.json` includes the test anchor and focused command. Production code was not changed.

Exact code/test head `d7d1b3225cb1fe1357fb5f63efda6c37bf0b52d8`:
- Frontend Build [44874469107](https://github.com/apexstudying-cmd/prepza/actions/runs/44874469107): PASS — 192 source/module tests + 5 offline Library tests, TypeScript, production build and architecture/launch-wiring audits.
- Backend Shared Extension Contract [44874469119](https://github.com/apexstudying-cmd/prepza/actions/runs/44874469119): PASS — 100 tests (6 warnings).
- Release Browser [44874469205](https://github.com/apexstudying-cmd/prepza/actions/runs/44874469205): PASS — 111 PostgreSQL QA tests, 0 failures (3,557 warnings); production image, disposable PostgreSQL/Redis and migrations, phone/tablet responsive checks, Shop buyer/seller/admin, B2B browser-to-ledger, Study Hub offline lifecycle, generated-material replay and podcast audio Blob replay passed.
- PostgreSQL Backup Restore [44874469196](https://github.com/apexstudying-cmd/prepza/actions/runs/44874469196): PASS — existing-database upgrade/data preservation and PostgreSQL 17 custom-format backup/restore.
- 17 triggered workflows succeeded; StudyHub Library Flow [44874469268](https://github.com/apexstudying-cmd/prepza/actions/runs/44874469268) was SKIPPED by path condition.
- Screenshot artifact: [14694698935](https://github.com/apexstudying-cmd/prepza/actions/runs/44874469205/artifacts/14694698935).

The browser callback remains in `app.py`; this is characterization, not extraction. The shared Paystack webhook remains inline because transfer helper definitions and failure/reversal money-state semantics are still unresolved. Provider tests remain mocked; no live Paystack request, payout, production data or deployment was used. Release remains BLOCKED.


## 2026-11-21 — Paystack browser callback extraction and exact-head verification

The previously characterized GET `/payment/paystack/callback` has now been moved from `app.py` into `paystack_callback_routes.py`, registered through `route_registry.py` at the original registration point. The registrar receives the existing payment-status synchronizer explicitly; the app passes a late-bound wrapper so existing request-time test injection remains intact. The route path, GET method, endpoint name, `reference`-before-`trxref` selection, missing-reference behavior, provider exception handling, status forwarding and SPA redirect are preserved. The webhook remains inline and was not changed. No live payment, payout, production data or deployment was performed.

Exact PR #79 head `e768ced975c62ba8d2aea7deeeabddf66cfa0386`:
- Backend Shared Extension Contract [44890448239](https://github.com/apexstudying-cmd/prepza/actions/runs/44890448239): PASS — Python compilation and backend boundary/compatibility tests.
- Frontend Build [44890448103](https://github.com/apexstudying-cmd/prepza/actions/runs/44890448103): PASS — TypeScript and production frontend build plus source/module and launch-wiring checks.
- Release Browser and Cross-System Regression [44890448099](https://github.com/apexstudying-cmd/prepza/actions/runs/44890448099): PASS — full release browser and cross-system suite.
- PostgreSQL Backup Restore Rehearsal [44890448130](https://github.com/apexstudying-cmd/prepza/actions/runs/44890448130): PASS — existing-database upgrade/data preservation and disposable custom-format backup/restore.
- Workflow inventory: 17 triggered workflows succeeded. StudyHub Library Flow [44890448198](https://github.com/apexstudying-cmd/prepza/actions/runs/44890448198) was SKIPPED by its path condition and is not counted as passing.

Next architecture work is not another payment-state rewrite. Keep the shared webhook in `app.py` until the absent `initiate_paystack_transfer`, `sync_paystack_transfer_status` and `_apply_paystack_transfer_result` implementations and their failure/reversal/idempotency semantics are recovered or specified. Do not invent money-state transitions or initiate payouts. Then continue with the remaining document/generation and base-chat boundaries using focused behavior contracts before extraction. Release remains BLOCKED; PR #79 remains draft and unmerged.


## 2026-11-22 — PR #79 stale-CSRF browser fixture repair and exact-head regression

The Release Browser run on intermediate head `9042e7b5e5fa9fe1a35245e8d57ee3d61ae1cfc9` stopped in the Shop buyer journey before message send because the fixture assertion read the wrong window property and expected the post-send count before sending. This was a test harness ordering/name defect. Commit [2627b210](https://github.com/apexstudying-cmd/prepza/commit/2627b21020b2841fc9ab8974ac6fca0581ad624b) now verifies the actual init-script counter is zero before send; the later assertions still require one injected stale-CSRF request and a 403 followed by the successful message response. The production retry remains limited to CSRF-specific 403 errors.

Exact application-code/test head `2627b21020b2841fc9ab8974ac6fca0581ad624b` on 2026-11-22:

- Frontend Build [44995165021](https://github.com/apexstudying-cmd/prepza/actions/runs/44995165021): **PASS** — 192 frontend source/module tests and 5 offline Library tests; TypeScript, production Vite build, screen/offline/calling audits and launch-wiring audit passed.
- Backend Shared Extension Contract [44995164973](https://github.com/apexstudying-cmd/prepza/actions/runs/44995164973): **PASS** — 102 tests, 6 warnings.
- Release Browser and Cross-System Regression [44995164976](https://github.com/apexstudying-cmd/prepza/actions/runs/44995164976): **PASS** — 111 PostgreSQL QA tests, 0 failures (3,557 warnings); production image, disposable PostgreSQL/Redis, Alembic and SQL migration ledger, responsive phone-small (360x800), phone-standard (390x844), tablet-portrait (768x1024), Shop buyer/seller/admin, B2B browser-to-ledger, Study Hub offline lifecycle, generated-material replay and podcast audio Blob replay all passed.
- PostgreSQL Backup Restore Rehearsal [44995164982](https://github.com/apexstudying-cmd/prepza/actions/runs/44995164982): **PASS** — populated prior-revision database upgrade preserved document/material rows and verified the current schema; PostgreSQL 17 custom-format backup restored into a separate disposable database and passed application smoke checks.
- Workflow inventory: **17 triggered workflows succeeded; 1 path-conditioned StudyHub Library Flow was SKIPPED** ([44995164917](https://github.com/apexstudying-cmd/prepza/actions/runs/44995164917)). The skipped workflow is not counted as a pass.
- Responsive screenshot artifact: [14742778901](https://github.com/apexstudying-cmd/prepza/actions/runs/44995164976/artifacts/14742778901).

The Shop browser run specifically passed the buyer in-app message path after one injected stale-CSRF 403 and exactly one successful retry. Seller listing/pause/sold and admin moderation/payment-review paths passed. B2B browser-to-ledger checks passed, including offscreen/offline no-charge, continuous-visibility qualification, lost-response UUID replay and duplicate-click protection.

Disposition: the ChatDetail stale-CSRF recovery path, Shop buyer/seller/admin browser journeys, responsive checks, B2B browser-to-ledger, 111-case PostgreSQL QA, Study Hub offline lifecycle, generated-material/podcast replay and populated-database/backup-restore rehearsal are **PASS** on the exact code/test head. StudyHub Library Flow is **SKIPPED** by path condition, not passed. Live Paystack/R2/SES/OpenAI/audio provider checks, ambassador payout semantics, retrieval/citation review, external monitoring, independent B2B viewability, human Home/PWA review and production deployment remain **NOT_TESTED / IN_PROGRESS / BLOCKED** as recorded in `qa/release_status.json`. Overall release remains **BLOCKED**.


## 23 November 2026 — E2EE key-backup route extraction and exact-head regression (PR #79)

The existing POST and GET `/keys/backup` handlers moved from `app.py` into `e2ee_key_backup_routes.py`. `route_registry.py` forwards the existing database, `UserKey` model and `require_csrf` decorator. Registration remains at the original location in `app.py`, before the Library routes. Endpoint names (`upload_key_backup`, `get_key_backup`), paths, methods, CSRF decorator order, session lookup, ownership scope, ciphertext/salt validation, size limits, error messages, database commit and JSON payloads are preserved. The legacy public-key helper functions remain in `app.py`; they are not active HTTP handlers and were not changed.

The new Flask/SQLite runtime contract verifies the exact route map, anonymous GET 401, POST CSRF 403, authenticated POST without a user 401, per-account backup isolation, missing-backup and missing-identity 404s, required fields, ciphertext/salt limits, upload persistence and download response. The route-registry contract verifies explicit dependency forwarding, module ownership and registration order. The backend workflow now compiles the new module and runs both new test files on PR and main-push paths. `qa/release_manifest.json` traces the route and runtime test.

**Exact application-code/test head:** [a7ef49122a69da11aec0db1ad42acbb3dd9f0785](https://github.com/apexstudying-cmd/prepza/commit/a7ef49122a69da11aec0db1ad42acbb3dd9f0785)

- Backend Shared Extension Contract [45123976442](https://github.com/apexstudying-cmd/prepza/actions/runs/45123976442): PASS — **106 passed, 13 warnings**; includes the new route runtime and registry contracts.
- E2EE Chat Validation [45123976473](https://github.com/apexstudying-cmd/prepza/actions/runs/45123976473): PASS — **16 passed, 7 warnings**; E2EE identity, realtime/chat regressions and frontend build passed.
- E2EE Security Regression [45123976542](https://github.com/apexstudying-cmd/prepza/actions/runs/45123976542): PASS — E2EE security/lifecycle invariants and realtime runtime regression passed.
- Frontend Build [45123976511](https://github.com/apexstudying-cmd/prepza/actions/runs/45123976511): PASS — **192 source/module tests + 5 offline Library tests**; TypeScript, production Vite build, screen-loading, offline/calling architecture, PWA and launch-wiring audits passed. The existing AdminSection dispatcher/controller/render-only view contracts are included.
- Release Browser/Cross-System Regression [45123976603](https://github.com/apexstudying-cmd/prepza/actions/runs/45123976603): PASS — **111 PostgreSQL QA tests, 0 failures, 3,557 warnings**; disposable PostgreSQL/Redis, Alembic and controlled migration ledger, phone/tablet responsive checks, Shop buyer/seller/admin journeys, B2B browser-to-ledger, Study Hub offline lifecycle, generated-material replay and podcast audio Blob replay passed.
- PostgreSQL Backup Restore Rehearsal [45123976525](https://github.com/apexstudying-cmd/prepza/actions/runs/45123976525): PASS — existing-database upgrade/data preservation and PostgreSQL 17 custom-format backup/restore passed.
- Workflow inventory: **17 triggered workflows succeeded;** StudyHub Library Flow [45123976623](https://github.com/apexstudying-cmd/prepza/actions/runs/45123976623) was SKIPPED by path condition and is not counted as a pass.
- Responsive screenshot artifact: [14795455524](https://github.com/apexstudying-cmd/prepza/actions/runs/45123976603/artifacts/14795455524).

The extraction changes no UI, navigation, public API, database schema, E2EE cryptographic protocol, Shop rule, payment flow, provider operation or production data. `app.py` is now 5,715 lines (45 inline route decorators); `frontend/src/App.tsx` remains 2,066 lines. The architecture refactor remains incomplete. The next backend review is the remaining document/generation and base-chat route/service dependency map. Release remains BLOCKED; live provider staging, missing ambassador transfer semantics, retrieval/citation accuracy, independent B2B viewability, external monitoring, human Home/PWA sign-off and deployment authorization remain open.


## 24 November 2026 — base-chat read-route extraction and exact-head CI status (PR #79)

The existing GET `/chats/<int:conversation_id>` and GET `/chats/<int:conversation_id>/messages` handlers were moved into `chat_read_routes.py`. `route_registry.py` forwards the existing `Message` model, `CHAT_PAGE_SIZE`, `_get_chat_or_404` membership guard and two existing serializers. The registrar is called immediately after `create_chat`, preserving the original route-registration position. Endpoint names, paths, GET methods, session authentication, membership-scoped 404 behavior, detail/message payloads, optional `before_id`, descending `(created_at, id)` ordering, page limit and chronological response order remain unchanged. No chat write, attachment, realtime, E2EE, frontend, UI, navigation or schema code changed.

Four focused Flask tests cover route/method identity, anonymous 401, membership guard, serialized detail, message order and page limit, query filtering, explicit dependency forwarding and registration position. The backend workflow compiles the module and runs this test file on pull requests and main pushes.

**Exact application-code/test head:** [9afc1eee078042c765d3ea48eb25ec78173830df](https://github.com/apexstudying-cmd/prepza/commit/9afc1eee078042c765d3ea48eb25ec78173830df)

- Backend Shared Extension Contract [45338511183](https://github.com/apexstudying-cmd/prepza/actions/runs/45338511183): **PASS — 110 tests, 13 warnings**, including module compilation and the four new Flask contracts.
- Frontend Build [45338511029](https://github.com/apexstudying-cmd/prepza/actions/runs/45338511029): **PASS — 192 source/module tests + 5 offline Library tests**, TypeScript, production Vite build, screen/offline/calling/PWA and launch-wiring audits.
- E2EE Chat Validation [45338510869](https://github.com/apexstudying-cmd/prepza/actions/runs/45338510869): **PASS** — E2EE/realtime/chat contracts and frontend build.
- E2EE Security Regression [45338510763](https://github.com/apexstudying-cmd/prepza/actions/runs/45338510763): **PASS**.
- PostgreSQL Backup Restore Rehearsal [45338510877](https://github.com/apexstudying-cmd/prepza/actions/runs/45338510877): **PASS** — populated prior-revision database upgrade preserved document/material records; PostgreSQL 17 custom-format backup restored and passed schema/data/Alembic and application smoke checks.
- Workflow inventory at documentation time: **16 triggered workflows succeeded, one path-conditioned StudyHub Library Flow was SKIPPED, and Release Browser [45338511095](https://github.com/apexstudying-cmd/prepza/actions/runs/45338511095) was IN_PROGRESS**. The full browser/cross-system gate is not marked PASS on this head until that run completes.

The previous exact code head `a7ef491` passed 111 PostgreSQL QA tests, responsive phone/tablet checks, Shop buyer/seller/admin, B2B browser-to-ledger and offline/generated-artifact journeys. That evidence is not silently transferred to `9afc1eee` while its Release Browser run is still running. The release ledger remains BLOCKED; live provider checks, retrieval/citation review, independent B2B viewability, external monitoring, human Home/PWA sign-off and deployment authorization remain open.