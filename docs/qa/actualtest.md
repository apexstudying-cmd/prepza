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

Current main is `0f393bd011d6047915cbb12a15acac87f21102c0`; the repository had no open PRs at verification time.

- **Frontend Build:** [run 43171345722](https://github.com/apexstudying-cmd/prepza/actions/runs/43171345722) passed 124 source/transform tests, 5 offline Library tests, functional-wiring and ORM/schema audits, TypeScript, service-worker validation and production Vite build.
- **Release Browser/Cross-System Regression:** [run 43171345717](https://github.com/apexstudying-cmd/prepza/actions/runs/43171345717) passed on the exact current main SHA. The job built the production image, started disposable PostgreSQL/Redis, applied Alembic and controlled SQL-ledger migrations, started the app, passed phone-small (360x800), phone-standard (390x844) and tablet-portrait (768x1024), passed Shop buyer/seller/admin browser journeys and B2B browser-to-ledger checks, passed 99 disposable PostgreSQL QA tests (3536 warnings), passed online/offline Study Hub and generated-artifact journeys, uploaded screenshots (artifact [13922288483](https://github.com/apexstudying-cmd/prepza/actions/runs/43171345717/artifacts/13922288483)), and cleaned up disposable services.
- **Release QA Trace:** [run 43171345768](https://github.com/apexstudying-cmd/prepza/actions/runs/43171345768) passed all 11 feature traces with 0 failures and 0 warnings on the exact current main SHA. The previous trace attempt on 732760 failed because three manifest entries still looked for extracted study models in `app.py`; commit 0f393 updates `qa/release_manifest.json` to point at `study_models.py` and `document_models.py`, and the rerun is green.
- **Current push workflow inventory:** all 13 observed push-triggered workflows on 0f393 completed successfully. This statement does not count conditional or PR-only workflows as passes.

### Populated-database migration and backup/restore

PostgreSQL Backup Restore Rehearsal [run 43171200015](https://github.com/apexstudying-cmd/prepza/actions/runs/43171200015) passed both jobs on code commit `73276018786bdaf007396c514fa0f358145138a7`:

1. **Existing database upgrade/data preservation:** created a representative prior-revision database at `20261005_chat_attach_source_doc`; seeded an existing document-content row and generated material before upgrade; upgraded to `20261030_shared_study_streak`; verified the document/material rows survived, `document_content.material_id` is nullable with its foreign key, Shop listing/saved/report tables and posting-payment review columns exist, and shared-streak tables exist.
2. **PostgreSQL custom dump/restore:** created a PostgreSQL 17 custom-format backup, restored it into a new disposable database, matched Alembic revision `20261030_shared_study_streak` and all 116 public tables, preserved the sentinel row, and connected the application to the restored database for a SQLAlchemy sentinel read. The disposable restore database and CI containers were cleaned up.

The migration/restore run is on 732760 and the full release-browser run is on 0f393. The only intervening commit updates the QA trace manifest to follow extracted model files, not application runtime behavior. Nevertheless, the strict final `clean_full_regression` gate remains **NOT_TESTED** until migration, backup/restore and the full release suite are rerun together on one exact SHA.

The Shop buyer/seller/admin journeys and responsive checks are now green on current main. The 16-image visual review artifact [13856133486](https://github.com/apexstudying-cmd/prepza/actions/runs/43024634046/artifacts/13856133486) remains the reviewed design reference. It confirms the compact underline tabs, navy/gold shell, white-card surfaces, 124px listing-image treatment and clearer price/title/meta hierarchy; it is not a student usability study. Real Paystack sandbox checkout/webhooks and real R2 object/header operations remain NOT_TESTED. The overall release remains BLOCKED; no production database, live payment, deployment, paid service or billable GPU operation was touched.
