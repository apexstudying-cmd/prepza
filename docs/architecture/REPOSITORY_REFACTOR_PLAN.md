# Prepza repository architecture and safe refactor plan

**Purpose:** make the repository easier to navigate and maintain without changing user-visible behavior, API contracts, authorization, persistence, billing, or product rules.

**Baseline source checkpoint:** `f747b0d95a6b81cb2868843093546a97e3d09fb5` (2026-10-31).
**Working branch:** `main`; PR #61, #62, #64, #65, #66, and #67 are merged (PR #62 merge `adbd7a9fc5bac3487e67f6f3ea319a3845e7401b`; PR #64 merge `7b0e9301543beabc5dee02af2388983737bada5c`; PR #65 merge `222b4011c40ddadaae3bdcf331022b79a78f5926`; PR #66 merge `29b582b6ca9e47b8a0cd725673c6be76b71358a1`). PR #56, #59, and the consolidated My Study integration PR #61 are also merged; the Achievements module is present on `main`. PR #67 was squash-merged to main as 62cdf80f2652746593b58f131c939f95442b0446.
**Status:** incremental refactor in progress. This document distinguishes current implementation from target structure.

## 1. Verified baseline

The initial source scan found:

| Area | Baseline size | Observation |
|---|---:|---|
| `app.py` | 10,332 lines; 318 top-level function/class declarations | Flask setup, SQLAlchemy models, shared helpers, and many HTTP routes coexist in one module. |
| `frontend/src/App.tsx` | 16,032 lines at the initial scan; 14,945 after PR #56; 14,887 after PR #59; 14,758 after the Achievements extraction on `main`; 14,573 after the My Study extraction in PR #61 (tested head `48cae152`); 14,129 on PR #62, merged as `adbd7a9fc5bac3487e67f6f3ea319a3845e7401b` after Group Detail was extracted; 13,739 on PR #64 after the two social follow screens were extracted; 12,979 after PR #66 merged the auth-flow screens; 12,622 on main after PR #67 merged Chat Options, shared chat types, and the Avi primitive. | Shared API/theme/icon/type definitions and several screens now live in focused modules. The app shell remains large and still needs staged extraction. |
| Frontend build | Long `prebuild` chain | Python scripts rewrite source files before TypeScript/Vite compilation. |
| Local QA runner | 11 test files; 95 test functions; 98 collected cases | Latest disposable PostgreSQL CI run passed 98/98; the detailed numbered test descriptions in `actualtest.md` are explicitly retained as a historical 74-case snapshot. |

A Graphify index of the baseline commit reported 3,946 code nodes, 8,259 edges, and 325 communities. Its index is a static dependency map, not a test run; its test links are incomplete and must not be treated as proof of coverage.

## 2. Current code ownership map

### Backend `app.py` route clusters

A declaration and route scan of the current `main` source (10,332 lines, 318 top-level functions/classes) shows these natural extraction boundaries:

| Approximate source range | Current responsibility | Candidate destination |
|---|---|---|
| 1–2,965 | Flask setup, extensions, models, shared helpers, background task wiring, health/bootstrap routes | `app_factory.py`, `extensions.py`, `models/`, `services/` |
| 2,965–3,736 | Signup, email verification, login, Google auth, logout, profile and account security | `routes/auth.py`, `routes/profile.py`, `services/auth/` |
| 3,736–3,907 and 8,924–9,117 | Payment history, payment/webhook and subscription transitions | `routes/payments.py`, `services/billing/` |
| 3,907–5,373 | Document upload/list/detail, reader progress/pages, summary, quiz, flashcards, mind map, podcast and tutor routes | `routes/documents.py`, `routes/generation.py`, existing AI/document services |
| 5,373–6,221 | Library publish/browse/save/report and admin moderation | `routes/library.py`, `services/library/` |
| 6,605–6,972 | Gamification summary, XP, streak, study-time and achievements | `routes/gamification.py`, existing streak/activity services |
| 6,972–8,174 | Groups, posts, comments, files, follows and social interactions | `routes/groups.py`, `routes/social.py` |
| 8,174–10,332 | Ambassador workflows, organisation and subscription endpoints, chat routes, administrative audit endpoints | Split by route family after mapping exact decorators and imported dependencies |

These are navigation boundaries, not a ready-made mechanical move list. The payment routes are intentionally shown as non-contiguous because the current file has payment logic in more than one region. Before moving a route, record its URL/method, decorators, dependencies, response shape, and test coverage.

### Backend model ownership map

The ORM classes are also grouped in the same `app.py` file. This inventory is based on the current class declarations and should guide a future model split:

| Domain | Current model declarations |
|---|---|
| Core identity and study content | `User`, `University`, `Program`, `ContentItem`, `Payment`, `SystemSetting`, `ViewProgress`, `Document`, `DocumentContent`, `DocumentPageText`, `DocumentReadingProgress`, `GeneratedMaterial` |
| AI and learning science | `AiJob`, `TutorConversation`, `TutorMessage`, `StudentLearningProfile`, `LearningConcept`, `LearningEvent`, `StudentConceptMastery`, `ConceptPrerequisite` |
| Library | `LibraryPublication`, `SavedLibraryMaterial`, `LibraryReport` |
| Gamification and study activity | `XpEvent`, `StudyStreak`, `StudyActivityLog`, `StudyTimeLog`, `QuizAttempt`, `FlashcardSession`, `UserAchievement`, `AiUsageLog` |
| Chat | `Conversation`, `ConversationParticipant`, `Message`, `MessageAttachment` |
| Groups and social | `Group`, `GroupMember`, `GroupPost`, `GroupPostComment`, `GroupPostLike`, `GroupQuestionVote`, `GroupFile`, `Follow`, `FollowRequest`, `Notification`, `NotificationPreference`, `Announcement`, `ContentReport`, `UserWarning` |
| Organisation and ambassador | `Organisation`, `OrganisationMember`, `Opportunity`, `Ambassador`, `Referral`, `AmbassadorPayout` |
| Audit, delivery and key material | `AuditLog`, `PushSubscription`, `UserKey` |

The first migration should be model extraction with no route movement: create a shared extension module, move one model domain at a time, keep model table names/constraints/relationships identical, and add metadata/table-creation and import-compatibility tests. Avoid importing `app.py` from model modules; that would create a circular dependency.

### Frontend largest remaining screen areas

The current `App.tsx` scan shows these large declarations still embedded in the app shell:

| Declaration | Approximate lines | Refactor priority |
|---|---:|---|
| `AdminSection` | 1,961 | High; split by admin domain after mapping state and permissions |
| `App` composition root | 538 | High; move navigation state/history into `app/navigation/` behind storage/history contract tests, leaving providers and route composition in `App` |
| `GroupDetailScreen` | Extracted in PR #62 | Existing 417-line screen body moved verbatim; app-shell feedback components passed as props |
| `FollowListScreen` + `FollowRequestsScreen` | Extracted in PR #64 (merged) | Existing follower/following and request screens moved to one social module; existing state and request flows retained |
| `ChatDetailScreen` | 406 | High; extract only after mapping E2EE, realtime and message-state dependencies |
| `SettingsScreen` | Extracted | Account, privacy, notification, appearance and security settings now live in `screens/settings/SettingsScreen.tsx` |
| `PodcastLibraryScreen` | Extracted | Podcast list now lives in `screens/podcast/PodcastLibraryScreen.tsx`; shared item metadata lives in `types/podcast.ts` |
| `AmbassadorScreen` | Extracted | `screens/ambassador/AmbassadorScreen.tsx` owns the application, dashboard, referrals and payout-request UI |
| `ChatsScreen` | 358 | High; extract after mapping realtime and encryption integration |
| `ChatOptionsScreen` | Extracted in PR #67 (pending verification) | The original 331-line body is preserved after explicit injection of the existing file-extension helper and image-type list; shared chat types and the existing Avi primitive now have owned modules. |
| `PodcastPlayerScreen` | 327 | Medium |
| `DocumentStudyScreen` | 323 | High; protect reader progress/offline contracts |
| `LibraryScreen` | 305 | Medium |
| `SignupScreen` | Extracted in PR #66 | Auth flow screens are owned by `screens/auth/AuthScreens.tsx`; route IDs and auth/CSRF behavior remain in the app shell. |

Line counts are approximate source spans between top-level declarations, not exact executable statement counts. They are useful for prioritization, not a complexity score.

## 3. What already exists

### Backend

The repository has already extracted several domain modules from the original Flask file, including:

- `ai_service.py`, `ai_economics.py`, `ai_reusable_generation.py`, and `ai_generation_store.py` for AI provider, economics, and artifact workflows.
- `document_pipeline.py`, `study_retrieval.py`, `study_retrieval_service.py`, and `study_retrieval_routes.py` for document processing and retrieval.
- `usage_billing.py`, `organisation_billing.py`, `discovery_billing.py`, and B2B modules for billing and campaign operations.
- `object_storage.py` for object-storage integration.
- `realtime_server.py`, `chat_event_queue.py`, and `chat_event_worker.py` for realtime delivery.

These modules are useful foundations. The next step is to map their import contracts and remove responsibilities from `app.py` gradually, not to move them blindly.

### Frontend

The frontend already has feature-oriented folders such as:

- `crypto/` — encrypted chat, calls, and related client security.
- `offline/` — offline study, generated materials, activity, and account isolation.
- `generation/` — generation screens and usage-plan logic.
- `admin/`, `organisation/`, and `share/` — extracted feature UI.

The original `App.tsx` still contains a large number of screens and shared definitions. Its first line is `// @ts-nocheck`; that should be retired gradually as modules are extracted and properly typed, not removed wholesale.

## 4. First frontend extraction

The architecture foundation (merged PR #56), Podcast Library extraction (merged PR #59), Achievements extraction on `main`, and My Study extraction in PR #61 have moved the following existing implementations without intentionally changing their behavior:

| New module | Responsibility |
|---|---|
| `frontend/src/lib/appApi.ts` | The existing App-level cookie-authenticated JSON fetch helper and `ApiError`. |
| `frontend/src/theme/theme.ts` | Existing brand palette and shared light/dark theme store. |
| `frontend/src/ui/icons.tsx` | Existing shared `Ic` icon map. |
| `frontend/src/types/academic.ts` | Shared university and program option types. |
| `frontend/src/screens/onboarding/CompleteProfileScreen.tsx` | Existing academic-profile completion screen. |
| `frontend/src/screens/ambassador/AmbassadorScreen.tsx` | Existing ambassador application, dashboard, referrals and payout-request screen. |
| `frontend/src/screens/settings/SettingsScreen.tsx` | Existing account, security, privacy, notification, appearance and deletion settings. |
| `frontend/src/screens/podcast/PodcastLibraryScreen.tsx` | Existing Podcast Library list; its shared UI primitives are passed as typed props from the app shell. |
| `frontend/src/types/podcast.ts` | Shared podcast item type, episode colour and duration formatting used by Home and Podcast Library. |
| `frontend/src/screens/gamification/AchievementsScreen.tsx` | Existing achievements list, progress/unlock presentation and share flow; shared response types live in `frontend/src/types/achievements.ts`. |
| `frontend/src/types/achievements.ts` | Typed achievement and response contracts shared with the profile and achievements screens. |
| `frontend/src/screens/study/StudyMaterialsScreen.tsx` | My Study document/material lists, online/offline merging, saved Library entries and existing-material replay. Shell feedback components and last-study persistence are passed through explicit props. |

`App.tsx` imports these modules and retains the application-level navigation integration. The legacy `frontend/src/lib/api.ts` remains separate: it has a different chat-oriented API and CSRF state contract. These two clients must not be merged until their behavioral differences are understood and tested.

The architecture foundation reduced `App.tsx` to 14,945 lines; Podcast Library reduced it to 14,887; Achievements brought it to 14,758; My Study reduced it to 14,573; Group Detail reduced it to 14,129; social follow screens reduced it to 13,739; Login and remaining auth-flow extraction reduced it to 12,979 on main after PR #66. PR #67 reduces the branch version to 12,630 by extracting Chat Options and related shared contracts/primitives. PR #62 code head `a342e822ca3a240257ecb5f8f84ad27d873985ac` passed Frontend Build run `41233691287` and Release Browser/Cross-System Regression run `41233691818`; post-merge run `41234848528` passed on merge commit `adbd7a9fc5bac3487e67f6f3ea319a3845e7401b`. The screen body was byte-for-byte compared against the pre-extraction `main` version after normalizing only the component signature and prop declaration. The exact tested branch is [PR #61](https://github.com/apexstudying-cmd/prepza/pull/61). These are incremental boundary improvements, not completion of the frontend or backend refactor.

## 5. Known architectural risks to address

1. **Build-time source rewriting.** The frontend `prebuild` chain modifies source code before compilation. A broad marker replacement removed the `ExploreScreen` wrapper while leaving its navigation route. The generation UI transform now stops before that wrapper and has a preservation guard plus a regression test. The wider transformation chain still needs auditing.
2. **Large application entry points.** `app.py` and `App.tsx` still own too many responsibilities.
3. **Implicit shared dependencies.** Many screens rely on helpers, types, theme values, and components declared elsewhere in `App.tsx`.
4. **Backend import coupling.** Existing runtime modules and tests import objects from `app.py`. Moving models or routes can create circular imports or break compatibility.
5. **Test coverage imbalance.** Backend route/runtime tests are more established than direct frontend component tests. Static source contracts and browser journeys complement each other but are not interchangeable.
6. **Documentation drift.** Test counts and some QA inventory details must be refreshed from the exact runner output after a successful full run.

## 6. Target structure

This is the direction for future changes, not a claim that all these directories already exist.

### Backend target

```text
backend/
  app.py                 # compatibility entry point / WSGI export
  app_factory.py         # application construction and configuration
  extensions.py          # SQLAlchemy, limiter, and shared extension instances
  models/                # SQLAlchemy models, grouped by domain
  routes/                # HTTP route registration / blueprints
  services/              # business workflows and domain rules
  repositories/          # database query and persistence boundaries
  integrations/          # OpenAI, Paystack, SES, R2, and other providers
  security/              # authentication, authorization, CSRF, and policy helpers
```

Migration order: map imports and tests; separate application construction from route/model declarations; extract low-coupling route domains; extract services/repositories; move models only after the shared database extension and import graph are stable. Keep existing root-level import paths as compatibility shims while consumers migrate.

### Frontend target

```text
frontend/src/
  app/                   # App shell, providers, navigation, route registry
  screens/               # screen-level compositions grouped by domain
    onboarding/
    study/
    library/
    chat/
    shop/
    admin/
  features/              # reusable domain behavior
  components/            # genuinely shared visual components
  lib/                   # API clients and general infrastructure
  theme/                 # design tokens and theme state
  ui/                    # icons and reusable primitives
  types/                 # shared domain contracts
  crypto/
  offline/
  generation/
  organisation/
  share/
```

Migration order: shared primitives and pure helpers first; then one screen/feature slice at a time; then move navigation composition. Preserve existing feature folders where they already have clear ownership. Do not create folders just to relocate files without improving boundaries.

## 7. Non-negotiable behavior-preservation rules

- Do not change route URLs, HTTP methods, request/response JSON, status codes, or authentication requirements as part of file movement.
- Do not change database models, migrations, table names, indexes, or data ownership during a structural refactor.
- Do not alter entitlement, pricing, billing, campaign-metering, or idempotency rules.
- Do not weaken document access checks, cohort permissions, E2EE boundaries, or account isolation.
- Do not change offline cache keys, serialization, or replay semantics without separate tests.
- Do not make live payment, email, AI, storage, or GPU calls as part of ordinary refactor QA.
- Keep work on a branch and merge only after the relevant CI/browser evidence is green.

## 8. Verification strategy

For every extraction:

1. Add or update a behavior/contract test before moving code.
2. Run focused tests and Python compilation where applicable.
3. Run the frontend TypeScript check and the production `pnpm run build` path, including prebuild transformations.
4. Run the full disposable PostgreSQL QA suite.
5. Run responsive, online/offline, generated-material, realtime/E2EE, and B2B browser journeys when the change touches those paths.
6. Compare API contracts and screen navigation before/after.
7. Update `docs/qa/actualtest.md`, `docs/qa/notes.md`, and `docs/NEXT_STEPS.md` only with evidence from the exact commit tested.

A passing compile is necessary but not sufficient. A passing test suite is evidence for the paths it covers, not proof that every screen or external provider has been verified.

## 9. Planned sequence

- [x] Establish an isolated refactor branch and draft PR.
- [x] Add a regression contract for the Summary build transform preserving `ExploreScreen`.
- [x] Fix the destructive Summary section boundary and add a post-transform preservation guard.
- [x] Wire relevant frontend and full release regression workflows to pull requests.
- [x] Extract the first shared frontend API/theme/icon/type modules and onboarding screen.
- [x] Complete full CI and browser verification for the current extraction (tested code commit `ba93150bf9df4348aada6d680bf4bfc4ddc595bb`; run 41222704363).
- [x] Reconcile the QA test record, learning notes and NEXT_STEPS tracker against the 11-file/98-case runner and successful CI output.
- [x] Extract Group Detail into a feature-owned module in draft PR #62; verify byte-for-byte screen body preservation, typecheck, production build, disposable database QA, responsive, B2B, and online/offline browser regression.
- [x] Extract the existing follower/following and follow-request screens into a shared social feature module with a dedicated API/state/navigation/type contract test; no screen body or interaction logic was rewritten. PR #64 merged as `7b0e9301543beabc5dee02af2388983737bada5c`; post-merge Frontend Build and Release Browser/Cross-System Regression passed.
- [ ] Continue frontend screen extraction in small, dependency-mapped slices.
- [ ] Design and implement backend app-factory/extensions boundaries with compatibility tests.
- [ ] Extract backend route/service domains incrementally.
- [ ] Reduce and eventually retire build-time source mutation after every transform has a committed source equivalent.

- [x] Extract the existing Login screen into `frontend/src/screens/auth/LoginScreen.tsx` in PR #65; the original 86-line component body is preserved byte-for-byte after normalizing the export declaration and narrowing the navigation callback type. Sign-in, resend-verification, Google OAuth, error handling, UI markup, and the existing `home` / `forgot-password` / `signup` destinations remain unchanged. Frontend Build, Student Frontend Contract, and Release Browser/Cross-System Regression passed (runs [41241016697](https://github.com/apexstudying-cmd/prepza/actions/runs/41241016697), [41241016700](https://github.com/apexstudying-cmd/prepza/actions/runs/41241016700), and [41241016614](https://github.com/apexstudying-cmd/prepza/actions/runs/41241016614)).


## 2026-11-05 status update — auth complete, chat options in verification

PR #66 is merged as 29b582b6ca9e47b8a0cd725673c6be76b71358a1. The five remaining auth-flow screens now live in frontend/src/screens/auth/AuthScreens.tsx; Login remains in LoginScreen.tsx. Frontend Build, Student Frontend Contract, and Release Browser/Cross-System Regression passed on the PR head, including production build, disposable database/migration checks, responsive browser journeys, B2B ledger checks, and online/offline generated-material flows.

PR #67 completed the Chat Options extraction into frontend/src/screens/chat/ChatOptionsScreen.tsx, moved shared chat data contracts into frontend/src/types/chat.ts, and extracted the shared avatar primitive into frontend/src/ui/Avi.tsx. The original screen body was byte-for-byte compared after only the documented signature/dependency-injection changes. CI first found the implicit app-shell Avi dependency; the exact visual component has now been extracted and reused. Verification passed on tested code head d19403803c3d8c851af2fbb6df5c8c8e6d73dcfc. Frontend Build passed 50 source/module tests, 5 offline Library tests, TypeScript, production build and architecture audits; Student Frontend Contract, Student Contract, E2EE Security/Chat, B2B, AI economics/generation, Admin Route, Study Navigation, Prepza Control API, and full Release Browser/Cross-System Regression passed. The release run passed production image, disposable database/migrations, responsive browser checks, B2B ledger, PostgreSQL QA, online/offline generated-artifact journeys, screenshot upload and cleanup. StudyHub Library Flow was skipped. Subsequent PR commits were documentation-only.

The backend is partially modularized, not fully extracted. Existing modules include AI provider/economics/generation, document pipeline/retrieval, billing, object storage, realtime delivery, and chat event delivery. The Flask entry module still contains application setup, SQLAlchemy model declarations, and many route families (approximately 10,332 lines at the audited baseline). Backend extraction remains a separate project: establish extensions and an application factory with import-compatibility tests first, then extract low-coupling route/service domains, and only then consider model movement. Do not describe the backend as extracted until the route/model ownership map and import graph show those responsibilities have actually moved.


PR #66 (auth-flow screens) is complete and merged. PR #67 (Chat Options, shared chat types, and shared Avi UI primitive) is complete and merged as 62cdf80f2652746593b58f131c939f95442b0446 after Frontend Build and full Release Browser/Cross-System Regression passed. The backend remains only partially modularized: existing service/integration modules are extracted, but the root Flask app still owns app setup, ORM models, and many route families. Backend work starts with extensions/app-factory/import compatibility rather than moving routes or models in one sweep.


## 2026-11-05 backend current-state inventory

The backend is **partially modularized, not extracted**. A source scan of the current app.py baseline found approximately 10,332 lines, 59 inline SQLAlchemy model classes, and 156 inline Flask route decorators. These are source-level counts, not a claim about the number of distinct live URL rules.

Already-separated backend areas include AI economics/generation, usage and organisation billing, discovery/B2B finance, admin operations/monitoring, document processing/retrieval, E2EE chat routes, offline activity, Shop, and request observability. app.py still owns global application construction, many route handlers, and the ORM model declarations.

### Concrete blockers to a conventional app factory

- app.py constructs a module-global Flask app and binds db = SQLAlchemy(app) during import. It also binds Flask-Limiter and initializes Sentry at module scope.
- db_runtime.py currently monkey-patches SQLAlchemy.__init__ so database pool options are applied before the engine is created. This is an initialization workaround, not a clean shared-extension boundary.
- Several modules still import the global app or its models from app.py; examples include chat_interactions.py, chat_group_routes.py, and prepza_control.py. Other modules use deferred imports from app inside functions, including document and generation paths.
- Existing register_* modules are not all pure registration functions: some perform schema/bootstrap work inside app.app_context() while they are registered during application import.
- tools/route_inventory.py and tools/route_coverage_matrix.py import the module-global app; retain that compatibility export throughout the migration.

### Safe backend migration order

1. Add import-compatibility and initialization-order tests before changing extension ownership. Preserve from app import app, db, Model for existing runtime modules, scripts, migrations, and tests.
2. Introduce a shared extensions.py boundary for the SQLAlchemy extension, then initialize it against the existing global Flask app after explicit database runtime configuration. Remove the constructor monkey-patch only after tests prove engine options, SQLite test behavior, session lifecycle, and PostgreSQL pool settings remain unchanged.
3. Map each model's foreign keys, relationships, importers, and Alembic metadata before moving model classes. Move models by bounded domain groups only after the shared extension is stable.
4. Convert route families to explicit blueprints/registration functions while preserving endpoint names, methods, auth/CSRF decorators, response bodies, status codes, and route order where observable.
5. Add app_factory.py only when route registration no longer depends on importing a partially initialized global app module. Keep app.py as a WSGI and legacy-import compatibility entry point until all consumers have migrated.

Do not combine extension extraction, model movement, route rewrites, and factory creation in one change. The first backend PR should be an initialization/extension-boundary change with import, configuration, migration, and route-inventory regression tests; it must not alter business logic or database schema.


## 2026-11-05 frontend extraction status — XP Progress

PR #68 extracts the active XPProgressScreen into frontend/src/screens/gamification/ProgressScreens.tsx, its response types into frontend/src/types/gamification.ts, and the unchanged shared formatStudyTime helper into frontend/src/lib/studyTime.ts. The original screen body was byte-for-byte compared after export/signature normalization. Frontend Build, Student Frontend Contract, Student Contract, Admin Route Contract, B2B, AI economics/generation, E2EE Security/Chat, Study Navigation, Prepza Control API, and full Release Browser/Cross-System Regression passed on tested code head cc665bce25bb570abe659d33e675b5f8acba690a. StudyHub Library Flow was skipped by workflow conditions. The subsequent PR commits updated documentation only.

The active study-streak and time-studied routes continue to use StudyActivityScreen; the older inline declarations remain untouched. Next frontend slices must continue to use live route composition and dependency maps rather than treating every old declaration as active UI.
