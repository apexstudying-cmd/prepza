# Prepza repository architecture and safe refactor plan

**Purpose:** make the repository easier to navigate and maintain without changing user-visible behavior, API contracts, authorization, persistence, billing, or product rules.

**Baseline source checkpoint:** `f747b0d95a6b81cb2868843093546a97e3d09fb5` (2026-10-31).
**Working branch:** `main`; PR #61, #62, #64, #65, #66, and #67 are merged (PR #62 merge `adbd7a9fc5bac3487e67f6f3ea319a3845e7401b`; PR #64 merge `7b0e9301543beabc5dee02af2388983737bada5c`; PR #65 merge `222b4011c40ddadaae3bdcf331022b79a78f5926`; PR #66 merge `29b582b6ca9e47b8a0cd725673c6be76b71358a1`). PR #56, #59, and the consolidated My Study integration PR #61 are also merged; the Achievements module is present on `main`. PR #67 was squash-merged to main as 62cdf80f2652746593b58f131c939f95442b0446. PR #68 (XP Progress), #69 (Library + Notifications), and #70 (shared SQLAlchemy extension) are also merged. PR #73 (public academic-catalog routes) was squash-merged as `d57cfecde2c98b59eec867c70cca4270ed2b1e73`. PR #74 (University and Program ORM models) was squash-merged as `6b82aba7bd7d167488c4a0e9921be6deb50a7648`.
**Status:** incremental refactor in progress. Consolidated PR #77 was squash-merged to `main` as `48a11afa5ca9b582d656cd83030f5dfefc87e22f` after exact code-head CI on `3fcc2b3fbd9605c14c22a6b587475a779d559150`. The current snapshot below is measured from merged main; this document distinguishes current implementation from target structure.

## 1. Verified baseline

The initial source scan found:

| Area | Baseline size | Observation |
|---|---:|---|
| `app.py` | 9,643 lines on main after merge `48a11afa` | Flask setup, the shared SQLAlchemy extension, remaining model declarations, shared helpers, and many HTTP routes still coexist in one module. |
| `frontend/src/App.tsx` | 16,032 lines at the initial scan; 14,945 after PR #56; 14,887 after PR #59; 14,758 after Achievements; 14,573 after My Study; 14,129 after Group Detail; 13,739 after social follow screens; 12,979 after auth screens; 12,622 after Chat Options; 12,044 after Notifications; 11,853 after Morio Tutor. Consolidated PR #77 extracted further screen, Admin, Podcast Player and public-shell boundaries; at tested code head `3fcc2b3`, merged as `48a11afa`, `App.tsx` is 5,034 lines. | The app shell remains the navigation/composition root and still needs bounded extraction of high-coupling flows. |
| Frontend build | Long `prebuild` chain | Python scripts rewrite source files before TypeScript/Vite compilation. |
| Current main source snapshot | `frontend/src/App.tsx`: 5,034 lines; `app.py`: 9,643 lines | Measured after PR #77 merge `48a11afa`; the exact tested code head was `3fcc2b3`. Both entry points still need future bounded extraction. |
| Local QA runner | 11 test files; 99 collected cases in the current release run | Latest disposable PostgreSQL CI run passed 99/99; the detailed numbered test descriptions in `actualtest.md` are historical snapshots unless explicitly refreshed. |

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

The shared extension boundary now exists in `extensions.py`. Continue model extraction one bounded domain at a time, keep model table names/constraints/relationships identical, and add metadata/table-creation and import-compatibility tests before each move. Avoid importing `app.py` from model modules; that would create a circular dependency.

### Frontend largest remaining screen areas

The current `App.tsx` composition root is 5,323 lines at the 9 November 2026 admin extraction head. The admin feature is no longer embedded in `App.tsx`; it now has explicit ownership boundaries:

| Admin module | Approximate lines | Responsibility |
|---|---:|---|
| `admin/AdminPlatform.tsx` | 118 | Platform shell, navigation groups, section routing, payment display metadata |
| `admin/AdminSection.tsx` | 172 | Small section dispatcher; retains the existing settings view |
| `admin/useAdminSectionController.ts` | 934 | Admin state, effects, API/CSRF calls, loading/error state and mutation handlers |
| `admin/AdminSectionCoreViews.tsx` | 783 | Typed render-only dashboard, users, Library/content, AI, payments, moderation and analytics views |
| `admin/AdminSectionPlatformViews.tsx` | 368 | Typed render-only system/infrastructure and communications views |
| `admin/AdminPanels.tsx` | 1,250 | Independent ambassador, opportunity, promotion, organisation, group, university and community panels |
| `admin/AdminShared.tsx` | 323 | Shared admin response types and presentation primitives |

The admin extraction moved the existing implementation out of the app shell rather than deleting functionality: `App.tsx` fell from 8,903 to 5,323 lines (3,580 lines / 40.2% smaller) at the tested code head. The admin view split then moved state/effects/API ownership into `useAdminSectionController.ts` and the render-only screens into two bounded view modules; `AdminSection.tsx` is now 172 lines. The controller remains the one large admin file (934 lines), deliberately keeping the existing state/effect lifetime intact rather than moving state into tabs and resetting it on navigation.

Other large declarations still embedded in the app shell include:

| Declaration | Approximate lines | Refactor priority |
|---|---:|---|
| `App` composition root / navigation state | 538 | High; move navigation state/history into `app/navigation/` behind storage/history contract tests, leaving providers and route composition in `App` |
| `GroupDetailScreen` | Extracted in PR #62 | Existing 417-line screen body moved verbatim; app-shell feedback components passed as props |
| `FollowListScreen` + `FollowRequestsScreen` | Extracted in PR #64 (merged) | Existing follower/following and request screens moved to one social module; existing state and request flows retained |
| `ChatDetailScreen` | 406 | High; extract only after mapping E2EE, realtime and message-state dependencies |
| `SettingsScreen` | Extracted | Account, privacy, notification, appearance and security settings now live in `screens/settings/SettingsScreen.tsx` |
| `PodcastLibraryScreen` | Extracted | Podcast list now lives in `screens/podcast/PodcastLibraryScreen.tsx`; shared item metadata lives in `types/podcast.ts` |
| `AmbassadorScreen` | Extracted | `screens/ambassador/AmbassadorScreen.tsx` owns the application, dashboard, referrals and payout-request UI |
| `ChatsScreen` | 358 | High; extract after mapping realtime and encryption integration |
| `AITutorScreen` | Extracted in PR #75 | Existing 183-line component body preserved; tutor cache/types move with the feature, while app-shell error/skeleton components are injected through typed props |
| `ChatOptionsScreen` | Extracted in merged PR #67 | The original 331-line body is preserved after explicit injection of the existing file-extension helper and image-type list; shared chat types and the existing Avi primitive now have owned modules. |
| `PodcastPlayerScreen` | Extracted | 349-line module at code head `76a435d`; offline Blob replay and reload recovery pass in the exact-head release browser run. |
| `DocumentStudyScreen` | 323 | High; protect reader progress/offline contracts |
| `LibraryScreen` | Extracted in merged PR #69 |
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

The backend is **partially modularized, not fully extracted**. The historical source baseline was approximately 10,332 lines with 59 inline SQLAlchemy model classes and 156 inline Flask route decorators. The current ownership counts after PR #74 are tracked at the end of this document. These are source-level counts, not a claim about the number of distinct live URL rules.

Already-separated backend areas include AI economics/generation, usage and organisation billing, discovery/B2B finance, admin operations/monitoring, document processing/retrieval, E2EE chat routes, offline activity, Shop, and request observability. app.py still owns global application construction, many route handlers, and the ORM model declarations.

### Concrete blockers to a conventional app factory

- app.py still constructs a module-global Flask app, configures Flask-Limiter, and initializes Sentry at module scope. PR #70 introduces a shared SQLAlchemy extension in extensions.py and explicitly initializes it from app.py; the app remains a global-app entry point.
- The former db_runtime.py constructor monkey-patch has been replaced on the backend refactor branch by explicit configure-before-init through extensions.py. PR #70 passed its focused extension contract and full release browser/cross-system regression; merge status is recorded below.
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


PR #68 (active XP Progress screen and shared study-time formatter) was squash-merged to main as 74dcebce5dd05ad08b5e3d77007cc5205f0b7bc0 after Frontend Build, student contracts, related admin/B2B/AI/E2EE/navigation/control checks, and full Release Browser/Cross-System Regression passed on tested code head cc665bce25bb570abe659d33e675b5f8acba690a. Later PR commits were documentation-only. This is another completed frontend slice, not completion of the repository-wide refactor.


## 2026-11-05 backend shared-extension boundary — PR #70 in verification

PR #70 introduces a module-global `db = SQLAlchemy()` in `extensions.py` and an explicit `init_extensions(app)` function. The function applies the existing PostgreSQL pool defaults before calling `db.init_app(app)`. `app.py` imports the same shared `db` object and initializes it after setting its existing configuration, preserving the legacy `from app import db` compatibility export used by models, route modules, Alembic, and scripts.

The constructor monkey-patch was removed from `db_runtime.py`. Existing PostgreSQL pool defaults, environment variable names, `setdefault` behavior, and SQLite/missing-URI bypass behavior are retained. No model, route, schema, migration, endpoint, or business logic is moved or changed in this slice.

Focused tests cover shared extension initialization with SQLite, PostgreSQL pool configuration, explicit-option precedence, and the absence of constructor patching. A dedicated GitHub Actions workflow compiles the entry point and extension modules and runs this focused contract. This PR remains draft until those checks and the full release regression complete. The global Flask app remains in app.py; no app factory is claimed.


## Backend ownership map — audited app.py baseline

The historical audited baseline contained 59 inline `db.Model` classes and 156 decorated Flask route handlers. Current source counts after PR #74 are recorded in the latest model-extraction section below. These are declaration counts, not a claim that each route decorator maps to a unique URL or that every model has no equivalent dynamically declared table in another module. Use this list as a starting map and confirm each model's relationships, importers, Alembic metadata, and runtime registration before moving it.

| Domain candidate | Inline model declarations to map | Main extraction cautions |
|---|---|---|
| Identity and platform | `User`, `SystemSetting`, `UserKey`, `AuditLog`, `RequestObservabilityEvent`, `PushSubscription`, `Notification`, `NotificationPreference`, `Announcement`, `ContentReport`, `UserWarning` | Session/auth decorators, admin permissions, request lifecycle hooks, notification producers, and observability scrubbing |
| Academic catalog | `ContentItem` (`University` and `Program` moved to `academic_models.py` in PR #74) | Seed/import scripts, public catalogue route contracts, and foreign-key consumers; preserve legacy `from app import University, Program` exports |
| Billing and organisations | `Payment`, `Organisation`, `OrganisationMember`, `Opportunity`, `Ambassador`, `Referral`, `AmbassadorPayout` | Paystack/webhook idempotency, B2B ledger integrity, entitlement writes, and dynamically registered billing models |
| Documents and learning | `DocumentContent`, `DocumentPageText`, `Document`, `DocumentReadingProgress`, `GeneratedMaterial`, `AiJob`, `TutorConversation`, `TutorMessage`, `StudentLearningProfile`, `LearningConcept`, `LearningEvent`, `StudentConceptMastery`, `ConceptPrerequisite`, `LibraryPublication`, `SavedLibraryMaterial`, `LibraryReport`, `XpEvent`, `StudyStreak`, `StudyActivityLog`, `StudyTimeLog`, `QuizAttempt`, `FlashcardSession`, `UserAchievement`, `AiUsageLog` | Retrieval permissions, document ownership, generated-material invalidation, offline sync, XP/streak time boundaries, and AI usage accounting |
| Chat and community | `Conversation`, `ConversationParticipant`, `Message`, `MessageAttachment`, `Group`, `GroupMember`, `GroupPost`, `GroupPostComment`, `GroupPostLike`, `GroupQuestionVote`, `GroupFile`, `Follow`, `FollowRequest` | E2EE key material, realtime event ordering, message idempotency, attachment authorization, and social notification side effects |

The 156 route decorators span the public shell/health, authentication, profile, document upload/read/study, AI generation, learning activity, library, subscription/payment, admin, ambassador, discovery/opportunities, social/community, and chat domains. The route extraction sequence should prioritize bounded route families already covered by standalone `register_*` modules, but only after import and extension ownership are stable. Preserve route paths, HTTP methods, endpoint names, decorator order, auth/CSRF behavior, response payloads, and registration timing.

Do not move all remaining models into a single models.py. Extract by bounded domain only after a generated import/relationship graph and Alembic metadata tests show no duplicate tables, missing relationships, changed naming, or migration drift.


### PR #70 verification and merge readiness

Backend Shared Extension Contract [run 42010022947](https://github.com/apexstudying-cmd/prepza/actions/runs/42010022947) passed all six focused tests and Python compilation. Full Release Browser/Cross-System Regression [run 42010022682](https://github.com/apexstudying-cmd/prepza/actions/runs/42010022682) passed production image build, disposable PostgreSQL/Redis startup, Alembic migrations, SQL migration-ledger checks, app startup, mobile/tablet browser checks, B2B browser-to-ledger regression, full PostgreSQL QA, online/offline and generated-artifact browser journeys, screenshot upload, and cleanup. The separate StudyHub Library Flow workflow was skipped by its conditions and is not counted as a pass.

The first focused workflow attempt failed only because the dedicated test environment omitted `psycopg2-binary`; the workflow was corrected to install the repository-pinned driver and the rerun passed. This is recorded as a test-environment correction, not an application-code failure.


### PR #70 post-merge status

PR #70 was squash-merged to main as 907658079a63a61439b42ea7de33d46ca31d0658. Backend Shared Extension Contract [42010022947] passed all six focused tests and compilation; Release Browser/Cross-System Regression [42010022682] passed all release gates. The shared extension boundary is now on main. The app remains a module-global Flask entry point; at the PR #70 code checkpoint, 59 models and 156 route decorators remained inline. Later PRs #73 and #74 reduce those inline counts while preserving all registered routes and table metadata. No separate post-merge workflow run is claimed.

## 2026-11-05 — Notifications backend route boundary (verified in merged PR #69)

The existing five notification HTTP handlers and serializer are extracted into `notification_routes.py` and registered with `register_notification_routes(app, db, Notification, require_csrf)` from app.py at the same route-registration position. The new module does not import the partially initialized app module. The serializer and 110-line route block were directly compared against the previous app.py source; contents are identical after indentation under the registration function. Route names, paths, methods, decorator placement, login and per-user authorization checks, announcement pin ordering, response shapes, and commits remain unchanged. `get_or_create_notification_prefs` and `should_notify` stay in app.py because they're used elsewhere.

After this extraction, app.py no longer owns the five notification route decorators (151 remain inline at the pre-merge snapshot); the five routes are registered by the new module. All 59 inline ORM model classes remain unchanged. PR #70's shared SQLAlchemy extension and `from app import db` compatibility work is preserved by rebasing this feature branch onto current main before final CI. The combined PR #69 final-head verification passed and the PR was squash-merged to main as `9a937eaca65f8995de5dc20cb3876577cc133445`.


## PR #69 final verification — Library and Notifications (2026-11-05)

PR #69 now combines the Library UI/types/shared helpers and module-aware prebuild transform with the full Notifications frontend/backend boundary. The UI component preserves its original 76-line body after only the documented module signature and app-shell loading/empty component injection. The backend moves the original 110-line serializer/handler block into `notification_routes.py`; the extracted function bodies compare byte-for-byte after indentation into the registrar. Routes are registered at the original point in app initialization, retaining names, paths, methods, CSRF decorators, auth/ownership checks, 24-hour announcement pinning, JSON shapes, and commit behavior. No schema or migration changed.

The branch was reconstructed on top of main commit `78c243a651cb8226f26db43d768f6b8b60f7955d`, preserving PR #70's `extensions.py` and explicit SQLAlchemy initialization. Tested application-code head: `0f61c64793cc32befb8ea22ba8ffedf68ef12412`. Frontend Build [42014965585] passed 69 source/module tests, 5 offline Library tests, functional wiring and ORM/schema audits, TypeScript, service-worker validation, and production build. Student Frontend [42014965317], Student Contract [42014965345], Admin Route [42014965329], E2EE Security [42014965431], E2EE Chat [42014965239], B2B [42014965382], AI Economics [42014965486], AI Generation [42014965230], Prepza Control API [42014965409], Study Navigation [42014965246], Study Hub Runtime [42014965289], and Backend Shared Extension Contract [42014965594] passed. Full Release Browser/Cross-System Regression [42014965433] passed production image, disposable PostgreSQL/Redis, migrations/ledger, responsive checks, B2B ledger regression, 98/98 PostgreSQL QA, online/offline generated-artifact browser journeys, screenshot upload, and cleanup. StudyHub Library Flow [42014965411] was skipped and is not counted as passing.

At this branch code head, `app.py` is 10,223 lines with 151 inline Flask route decorators and 59 inline ORM models; `notification_routes.py` owns five of the 156 total route registrations. This is incremental extraction, not backend completion. PR #69 is merged to main as `9a937eaca65f8995de5dc20cb3876577cc133445`; the frontend's high-risk chat, document study/reader, admin, generation, and app-navigation boundaries and 59 inline models remain future work.

## 2026-11-05 — Public academic catalog route extraction (PR #73; verified)

The original public `list_universities` and `list_programs` handlers now live in `academic_catalog_routes.py`, registered through `register_academic_catalog_routes(app, University, Program)` at their original initialization position after the models and before signup. Both handler bodies were compared with the previous main source and are byte-for-byte identical after removing registrar indentation. The original Flask endpoint names are explicitly retained.

The move preserves GET paths/methods, active-only filtering, alphabetical ordering, missing/inactive university 404 response, and JSON field shapes. No ORM model, migration, database schema, permission, signup flow, or business rule was changed. Focused contract run [42019950835](https://github.com/apexstudying-cmd/prepza/actions/runs/42019950835) passed Python compilation and all 5 tests.

On tested application-code head `55fbf1ce588c6650b5171bd4c752e10055614df7`, Student Frontend Contract [42019950427], Admin Route Contract [42019950566], B2B Contract [42019950492], E2EE Security [42019950395], Study Navigation [42019950431], Prepza Control API [42019950757], AI Economics [42019950545], and Kokoro syntax [42019950385] passed. Full Release Browser/Cross-System Regression [42019950561] passed production image, disposable PostgreSQL/Redis, Alembic migration and controlled SQL-ledger checks, app startup, mobile/tablet browser checks, B2B browser-to-ledger regression, 98/98 PostgreSQL QA tests, online/offline and generated-artifact browser journeys, screenshot upload, and cleanup.

The application source at this tested head is 10,191 lines with 149 inline `@app` route decorators and 59 inline ORM model classes. The total route registrations remain 156: 149 inline in `app.py`, five in `notification_routes.py`, and two in `academic_catalog_routes.py`. This is a small route-family extraction, not full backend extraction or app-factory conversion.

### PR #73 post-merge status

PR #73 was squash-merged to `main` as `d57cfecde2c98b59eec867c70cca4270ed2b1e73`. The focused Backend Academic Catalog Route Contract [42019950835] passed all five tests and Python compilation; full Release Browser/Cross-System Regression [42019950561] passed responsive, B2B, 98/98 PostgreSQL QA, online/offline generated-artifact journeys, screenshot upload, and cleanup. The tested source remains 10,191 lines in `app.py`, with 149 inline route decorators and 59 inline ORM classes. No separate post-merge workflow run is claimed.

## 2026-11-05 — Academic catalog ORM model extraction (PR #74; verified)

The existing `University` and `Program` model class bodies have moved from `app.py` to `academic_models.py` and continue to use the single shared `extensions.db` object. `app.py` imports both names at the original declaration point after `User` and before `ContentItem`, preserving the legacy `from app import University, Program` exports used by seed scripts, browser tests, admin runtime modules, and other consumers. The original 864-character class block was compared with the moved block and is byte-for-byte identical.

Four new model contracts verify shared SQLAlchemy metadata, table names, column lengths/nullability, uniqueness, defaults, the `program.university_id → university.id` foreign key, and the app-level compatibility export/import order. The existing six shared-extension tests also remain active. Backend Shared Extension Contract [42021795293](https://github.com/apexstudying-cmd/prepza/actions/runs/42021795293) passed compilation and all 10 tests.

On tested code head `f7c8ec327483f4d5170bfa0aa4ec60285d81574f`, Student Frontend [42021795416], Student Contract [42021795394], Admin Route [42021795332], B2B [42021795333], E2EE Security [42021795546], E2EE Chat [42021795286], Study Navigation [42021795308], Prepza Control API [42021795303], AI Economics [42021795374], AI Generation Architecture [42021795427], and Kokoro syntax [42021795321] passed. Release Browser/Cross-System Regression [42021795474] passed production image, disposable PostgreSQL/Redis, Alembic migrations and SQL ledger, app startup, responsive mobile/tablet checks, B2B browser-to-ledger regression, 98/98 PostgreSQL QA tests, online/offline Study Hub and generated-artifact journeys, screenshot upload, and service cleanup. StudyHub Library Flow [42021795345] was skipped by workflow conditions and is not counted as a pass.

At this tested head, `app.py` is 10,174 lines with 57 inline ORM model classes and 149 inline Flask route decorators. `academic_models.py` owns the two moved models, so the same 59 model classes remain registered in the same SQLAlchemy metadata. Across route modules, all 156 route registrations remain available: 149 inline in `app.py`, five in `notification_routes.py`, and two in `academic_catalog_routes.py`. No schema, migration, table name, column, constraint, foreign key, or app-factory behavior changed.

### PR #74 post-merge status and current ownership counts

PR #74 was squash-merged to `main` as `6b82aba7bd7d167488c4a0e9921be6deb50a7648`. The tested source head `f7c8ec327483f4d5170bfa0aa4ec60285d81574f` passed the Backend Shared Extension Contract [42021795293] (10/10 tests) and full Release Browser/Cross-System Regression [42021795474] (including 98/98 PostgreSQL QA and online/offline generated-artifact browser journeys). The subsequent commits only updated documentation.

Current `main` after PR #74: `app.py` is 10,174 lines with 57 inline `db.Model` declarations and 149 inline route decorators. `academic_models.py` owns `University` and `Program`. Together, the same 59 model classes remain registered on `extensions.db.Model.metadata`; all 156 route registrations remain intact (149 in `app.py`, five in `notification_routes.py`, two in `academic_catalog_routes.py`). No migration/schema change or app-factory conversion was included.


## 2026-11-05 — Morio AI Tutor extraction (PR #75; verified)

The active `AITutorScreen` now lives in `frontend/src/screens/tutor/AITutorScreen.tsx`. The original 183-line component body compares byte-for-byte with the pre-extraction source after normalizing the module export, narrowing the navigation callback to its existing `home` and `upload` destinations, and injecting the already-existing `GenerationError`, `DelayedScreenSkeleton`, and `SkeletonAITutor` components as props. `TutorMsg`, `PickableDoc`, and the module-scoped per-document `AI_TUTOR_CACHE` moved with it.

The `ai-tutor` route composition remains in App.tsx. The module keeps the existing document readiness filter, `/documents` and `/me` requests, tutor conversation GET, tutor message POST, CSRF header/body, session cache behavior, 20-second `tutor_chat` heartbeat, existing 429/503 messages, and the current navigation actions. The screen no longer relies on app-module imports. The repository prebuild search did not find a transformer that rewrites AITutorScreen, so no transformer was modified.

Verification on tested code head `f5f8afb34a8d74c742de4b4d33762ec882b05a81`:
- Frontend Build [42022943650](https://github.com/apexstudying-cmd/prepza/actions/runs/42022943650): focused source contracts, offline Library regression, functional wiring/ORM audits, TypeScript, service-worker checks, and production build passed.
- Student Frontend [42022943640](https://github.com/apexstudying-cmd/prepza/actions/runs/42022943640), Student Contract [42022943669](https://github.com/apexstudying-cmd/prepza/actions/runs/42022943669), Admin Route [42022943910](https://github.com/apexstudying-cmd/prepza/actions/runs/42022943910), B2B [42022943975](https://github.com/apexstudying-cmd/prepza/actions/runs/42022943975), E2EE Security [42022943817](https://github.com/apexstudying-cmd/prepza/actions/runs/42022943817), E2EE Chat [42022943967](https://github.com/apexstudying-cmd/prepza/actions/runs/42022943967), AI Economics [42022943628](https://github.com/apexstudying-cmd/prepza/actions/runs/42022943628), AI Generation [42022943687](https://github.com/apexstudying-cmd/prepza/actions/runs/42022943687), Study Navigation [42022943704](https://github.com/apexstudying-cmd/prepza/actions/runs/42022943704), and Prepza Control API [42022943818](https://github.com/apexstudying-cmd/prepza/actions/runs/42022943818) passed.
- Release Browser/Cross-System Regression [42022943630](https://github.com/apexstudying-cmd/prepza/actions/runs/42022943630) passed production image, disposable PostgreSQL/Redis and Alembic/ledger, app startup, mobile/tablet checks, B2B ledger, 98/98 PostgreSQL QA, online/offline and generated-artifact journeys, screenshots, and cleanup.
- StudyHub Library Flow [42022943808](https://github.com/apexstudying-cmd/prepza/actions/runs/42022943808) was skipped by workflow conditions and is not counted as passing.

The tested PR #75 application-code head is `f5f8afb34a8d74c742de4b4d33762ec882b05a81`; subsequent commits on the PR branch update documentation only. The frontend refactor remains incomplete: ChatDetail/Chats, DocumentStudy/Reader, generation flows, Podcast Player, AdminSection/panels, and app-shell navigation remain to be mapped and extracted. Backend extraction remains a separate, staged effort.


## 2026-11-05 — Splash and Edit Profile extraction (PR #77; current branch)

The current PR #77 branch moves the existing SplashScreen into frontend/src/screens/onboarding/SplashScreen.tsx (63 lines) and EditProfileScreen into frontend/src/screens/profile/EditProfileScreen.tsx (224 lines). App.tsx is 11,591 lines on this branch, down from 11,853 before these two extractions. Both component bodies were compared directly with the base main declarations and are byte-for-byte identical after only the documented module signature, brandline prop, narrowed navigation callback, and local response-type adjustments.

The SplashScreen move exposed a prebuild-transform ownership assumption. The Study Navigation patch previously expected the component's state marker inside App.tsx and returned early whenever the historical patch marker existed. It now supports both inline legacy and module-owned SplashScreen modes, passes the app-shell offline-resume callback into the module, and continues idempotent transforms even when the historical marker is already present. The production-build verifier and workflow anchors now assert the extracted module contract.

Frontend Build [42030603950] passed 76 source/module tests, 5 offline Library regression tests, TypeScript, service-worker validation, production build and architecture audits. Student Frontend [42030604065], Student Contract [42030603908], Admin Route [42030604002], B2B [42030603900], AI Generation [42030604051], AI Economics [42030604139], Prepza Control API [42030603917], E2EE Security [42030603959], and E2EE Chat [42030604078] passed. Full Release Browser/Cross-System Regression [42030603969] passed production image, disposable PostgreSQL/Redis, 43 migration files and controlled SQL ledger, app startup, mobile/tablet browser checks, B2B metering, 98/98 PostgreSQL QA, online/offline Study Hub and generated-artifact journeys, screenshot upload, and cleanup. The tested application-code head is unchanged by subsequent documentation-only commits.

The frontend refactor remains incremental, not complete. Remaining large or high-coupling boundaries include ChatsScreen/ChatDetailScreen (E2EE/realtime), DocumentStudyScreen/DocumentReaderScreen (offline/progress), AdminSection and admin panels (permissions/multi-domain state), generation flows, Podcast Player, Home/Explore, opportunity/profile flows, and app-shell navigation. Continue only with dependency mapping, explicit props, source-preservation comparisons, and behavior contracts. Do not redesign screens, change API contracts, or move high-risk logic without dedicated regression evidence.


### New Chat extraction follow-up — PR #77

NewChatScreen now resides in frontend/src/screens/chat/NewChatScreen.tsx (159 lines). The PR branch App.tsx is 11,440 lines, down 413 from the starting 11,853 lines. Its implementation was compared with base main and preserved byte-for-byte apart from the module export and narrowed callback type. The module contract protects debounced search and cleanup, direct chat create/reuse, group validation/creation, CSRF, participant selection, and route navigation.

Frontend Build [42031983870] passed 78 source/module tests, 5 offline Library tests, TypeScript, service-worker checks, production build, and architecture audits. Student Frontend, Student Contract, Admin Route, B2B, AI, Prepza Control API, E2EE Chat and E2EE Security workflows passed. Full Release Browser/Cross-System Regression [42031984075] passed on the New Chat code head: production image, disposable PostgreSQL/Redis, 43 migration files and controlled ledger, mobile/tablet browser checks, B2B metering, 98/98 PostgreSQL QA, online/offline Study Hub and generated-artifact journeys, screenshot upload, and cleanup. Subsequent PR commits are documentation-only.


### Additional small screen-boundary extractions — 2026-11-05

TimeStudiedScreen now lives in frontend/src/screens/gamification/TimeStudiedScreen.tsx (61 lines), and ShareOppForm in frontend/src/screens/opportunities/ShareOppForm.tsx (45 lines). Their moved component bodies were directly compared with base main and are byte-for-byte identical after normalising only exports and narrowed callback types. Focused source contracts protect the original study-time loading/cancellation/period-selection behavior and the opportunity form's controlled fields, categories and navigation. Latest CI and full release regression are pending on the new head.


### Student Profile extraction follow-up — PR #77

StudentProfileScreen and its PublicProfile/FollowSummary types now live in frontend/src/screens/profile/StudentProfileScreen.tsx (164 lines). App.tsx is 11,286 lines on this branch, 567 lines below the 11,853-line starting point. The component body was compared directly to base main and preserved byte-for-byte after normalising only module export and narrowed callback/back-screen types. The app-shell back-screen state was narrowed to its actual two values.

Frontend Build [42033518073] passed 80 source/module tests, 5 offline Library tests, TypeScript, service-worker validation, production build and architecture audits. Student Frontend, Student Contract, Admin Route, B2B, AI, control API, and E2EE Chat workflows passed. Full Release Browser/Cross-System Regression [42033518119] and E2EE Security Regression [42033518226] were still running at the time of this update and remain required before merge.


### Study Streak module — 2026-11-05

StudyStreakScreen and its response types are now owned by frontend/src/screens/gamification/StudyStreakScreen.tsx. The screen body matches base main byte-for-byte after export and callback-type normalisation. The module preserves its existing month navigation, cancellation, tap-to-reveal calendar day, milestone, and share-sheet behavior. A prior typecheck caught and prompted correction of the existing share-sheet callback in TimeStudiedScreen; the corrected route union is now covered by a source contract. The latest Frontend Build [42034876037] passed 86 frontend source/module contracts, 5 offline Library tests, TypeScript, production build, architecture audits and launch-wiring verification. Full release regression [42034875673] remains pending.


### Profile screen boundary — 2026-11-05

ProfileScreen now lives in screens/profile/ProfileScreen.tsx. Its PROFILE_CACHE moved with it; ProfileMe and HomeDocument are shared in types/profile.ts, while GamificationSummary is in types/gamification.ts. App.tsx retains route dispatch, parent-owned state and the existing SkeletonProfile component (passed into the screen). The screen body was verified byte-for-byte against base main after export/prop/callback type normalisation. The first typecheck identified dynamic profile-card destinations still typed against the App-local Screen alias; the extracted module now uses an equivalent local ProfileScreenRoute union. Frontend Build [42036291254] passed 88 frontend source/module contracts, 5 offline Library tests, TypeScript, production build, architecture audits and launch-wiring verification. Full release regression [42036291297] remains queued.


### Document Ready module — 2026-11-05

DocReadyScreen now resides in screens/study/DocReadyScreen.tsx; DocumentDetail is shared from types/documents.ts. Existing TopBar is injected by App.tsx, and the route dispatcher remains centralized. The original screen body was verified byte-for-byte after export/prop/local-route-type normalisation. Frontend Build [42036938429] passed 90 frontend source/module contracts, 5 offline Library tests, TypeScript, production build, architecture audits and launch-wiring verification. Full release regression [42036938563] remains queued.


## 2026-11-09 — Public application-shell routes included in consolidated integration

The root document, root-scoped service worker, and health endpoints are now owned by `public_shell_routes.py` on the same integration branch as the current frontend screen extractions. `register_public_shell_routes(app, db, limiter, sweep_expired_opportunities_safe)` receives dependencies explicitly and does not import the partially initialized Flask entry module. Registration occurs after the existing activity hook and before academic catalog registration, preserving initialization order. Focused tests protect route methods and endpoint names, static-file serving, service-worker MIME/cache headers, health SQL probe, limiter exemption, sweep behavior, and error response.

This consolidates the previous standalone PR #76 implementation into PR #77. Verification is pending on the combined head; do not treat the route move as release-verified until its focused route contracts, shared-extension contract, frontend build, and full cross-system release regression pass. No app-factory conversion, ORM model move, middleware change, schema change, or migration is part of this step.

## 2026-11-09 — Consolidated refactor verification closeout

Verified against the exact PR #77 head `b37cad55f3fb6e389dead1d4ca19df2f31265674` (base `main` at `459c96cd7179810499edbec266e1f5deab3f9d4c`). PR #77 contains 30 changed files (+2,191/−1,236 lines) and remains open, unmerged, and mergeable. On this exact head, 16 GitHub Actions workflows passed: Frontend Build; Study Navigation Polish; Student Frontend Contract; Student Contract Validation; Admin Route Contract; Prepza Control API; Backend Shared Extension Contract; Backend Academic Catalog Route Contract; B2B Contract Validation; AI Generation Architecture; AI Economics Validation; E2EE Chat Validation; E2EE Security Regression; Study Hub Runtime Regression; Kokoro GPU Worker Validation; and Release Browser and Cross-System Regression. (The workflow inventory contains 16 successful runs plus one skipped run.)

Release Browser and Cross-System Regression [run 42581515451](https://github.com/apexstudying-cmd/prepza/actions/runs/42581515451) passed on this exact SHA: production image build; disposable PostgreSQL/Redis startup; Alembic migrations and controlled migration-ledger checks; app startup; mobile/tablet responsive browser checks; B2B browser-to-ledger metering regression; full disposable PostgreSQL QA; online/offline and generated-artifact browser journeys; responsive screenshot upload; and service cleanup. The separate StudyHub Library Flow [run 42581515401](https://github.com/apexstudying-cmd/prepza/actions/runs/42581515401) was skipped by workflow conditions and is not counted as a pass. The failure-log collection step was skipped because the job succeeded.

At this exact PR head, `frontend/src/App.tsx` is 10,745 lines and `app.py` is 10,139 lines. This is a structural refactor, not completion of all repository modularization: both root files remain substantial and further bounded extraction can continue later. No production deployment, live provider verification, or production-database migration is implied by these CI results.

PR #77 remains open and unmerged. These checks verify the integration branch only; `main` does not contain these changes until the PR is merged. Do not merge without the user's explicit approval.


## 2026-11-11 — Admin domain-panel split (PR #77)

The 1,250-line `AdminPanels.tsx` implementation has been separated into two feature-owned modules while preserving the original component bodies and named import surface. `AdminGrowthPanels.tsx` (531 lines) owns the existing ambassador and opportunity review panels. `AdminDomainPanels.tsx` (728 lines) owns the existing promotions, organisations, groups, universities and community panels. `AdminPanels.tsx` is now a three-line compatibility barrel re-exporting the same seven component names consumed by `AdminSection.tsx`. No component state, effects, API paths, CSRF headers, route keys or mutation handlers were intentionally changed.

A focused boundary contract protects the barrel exports, component ownership, file-size bounds and existing API/CSRF ownership. The legacy Admin platform ownership contract was updated to follow the re-exported modules instead of assuming every component implementation must remain in one file. Frontend Build [run 43001624586](https://github.com/apexstudying-cmd/prepza/actions/runs/43001624586) passed on code head `99796c39e81f2ed79949e9b492b31a5541de5d8b`: 120 focused source/transform tests, 5 offline Library tests, both audits, TypeScript, service-worker validation and production Vite build. The complete Release Browser/Cross-System Regression is still running at this update; do not infer its result from Frontend Build.


## 2026-11-11 — Exact-head release regression closeout for Admin domain-panel split

Release Browser and Cross-System Regression [run 43001889849](https://github.com/apexstudying-cmd/prepza/actions/runs/43001889849) passed on exact PR #77 head `949530b97fea9df8557eddbd408f2c667130c511`. The job built the production image; started disposable PostgreSQL/Redis; passed Alembic and controlled migration-ledger checks; passed phone-small (360x800), phone-standard (390x844), and tablet-portrait (768x1024) browser checks; passed B2B browser-to-ledger metering; passed the full disposable PostgreSQL QA suite; passed online/offline Study Hub and generated-artifact journeys; uploaded 12 responsive screenshots (artifact [prepza-mobile-responsive-screenshots](https://github.com/apexstudying-cmd/prepza/actions/runs/43001889849/artifacts/13845874778)); and cleaned up disposable services/volumes. Frontend Build [run 43001890115](https://github.com/apexstudying-cmd/prepza/actions/runs/43001890115) also passed on the same exact head. Of 17 workflows on the head, 16 succeeded and StudyHub Library Flow was skipped by workflow conditions; the skipped workflow is not counted as a pass. This verifies the PR branch, not production deployment or live provider behavior.

This closes the CI verification for the current PR #77 Admin domain-panel extraction and combined refactor head. It does not close the overall release: `app.py` remains a large backend entry module, the Shop visual-system and detailed user-flow audit remain open, and provider/staging/retrieval/observability gates remain separate. PR #77 remains open and unmerged; do not merge or deploy without explicit approval.


## 2026-11-11 — Podcast Player extraction and Shop browser verification (PR #77)

The Podcast Player boundary is now module-owned in `frontend/src/screens/podcast/PodcastPlayerScreen.tsx` (349 lines). The screen receives its existing API, offline-cache, activity-credit and navigation responsibilities through explicit props/callbacks. A cached service-worker `ready` descriptor is not treated as an offline audio asset: when offline, the component resolves the account-scoped cached Blob first. Exact-head CI verifies the Blob opens offline and after reload, podcast activity credit continues while hidden, and pausing playback stops credit.

At exact code head `76a435d91db27ca09292e20d16c31ec2b34c9884`, `frontend/src/App.tsx` is 5,034 lines and `app.py` is 9,643 lines. AdminSection and Admin domain-panel extraction are also present in this consolidated PR. Remaining frontend extraction work should focus on ChatDetail/Chats, DocumentStudy/Reader, generation flows, Home/Explore and app-shell navigation; backend modularization remains separate.

Shop's short visual consistency pass replaces section pills with compact underline tabs, normalizes listing-card image/placeholder height to 124px and improves title/price/meta hierarchy. Existing routes, 44px targets, navy/gold brand, seller fee/payment behavior, buyer direct-contact boundary and fixed global navigation are preserved. The new `scripts/test_browser_shop_journeys.py` verifies buyer browse/detail/save/Saved/report/contact, seller My Listings/pause/sold/paid-form disclosure and admin approve/reject/report/payment-review handling. Its admin approval fixture uses a synthetic uploaded-photo key; it does not assert a real R2 upload.

Frontend Build [run 43023202179](https://github.com/apexstudying-cmd/prepza/actions/runs/43023202179) and Release Browser/Cross-System Regression [run 43023202418](https://github.com/apexstudying-cmd/prepza/actions/runs/43023202418) passed on exact code head `76a435d91db27ca09292e20d16c31ec2b34c9884). The release job passed production image build, disposable migrations/ledger, responsive phone/tablet, Shop role journeys, B2B browser-to-ledger, 99 disposable PostgreSQL QA tests, online/offline generated-artifact replay, screenshot upload and cleanup. Of 17 workflows, 16 succeeded and StudyHub Library Flow was skipped. Screenshot artifact: [13855748767](https://github.com/apexstudying-cmd/prepza/actions/runs/43023202418/artifacts/13855748767).

PR #77 remains open and unmerged. Live Paystack sandbox/R2 provider verification, production deployment and unrelated release gates are not covered by these results.


## 2026-11-12 — Consolidated PR #77 merged to main

The single consolidated [PR #77](https://github.com/apexstudying-cmd/prepza/pull/77) was squash-merged as 48a11afa5ca9b582d656cd83030f5dfefc87e22f after exact-head verification on 3fcc2b3fbd9605c14c22a6b587475a779d559150. Frontend Build [43024634109](https://github.com/apexstudying-cmd/prepza/actions/runs/43024634109) passed 124 source/transform contracts, five offline Library tests, audits, TypeScript, service-worker validation and production Vite build. Release Browser [43024634046](https://github.com/apexstudying-cmd/prepza/actions/runs/43024634046) passed production-image build, disposable PostgreSQL/Redis, Alembic and controlled migration ledger, phone/tablet checks, Shop buyer/seller/admin journeys, B2B browser-to-ledger, 99 PostgreSQL tests, online/offline generated-artifact journeys, screenshot upload and cleanup. Sixteen of 17 applicable workflows succeeded; StudyHub Library Flow was skipped and is not counted.

Current main source sizes are App.tsx 5,034 lines and app.py 9,643 lines. Admin is now divided into the 172-line dispatcher, 934-line unconditional controller hook, 783/368-line typed render-only view modules, 531/728-line growth/domain panel modules and a three-line compatibility barrel. Podcast Player is 349 lines. The exact source snapshot was checked from GitHub after merge.

The Shop visual review inspected the 16-image screenshot artifact [13856133486](https://github.com/apexstudying-cmd/prepza/actions/runs/43024634046/artifacts/13856133486). The compact underline tabs, navy/gold header, white-card surfaces, 124px listing image treatment, readable price/title/meta hierarchy and phone/tablet layouts are now more consistent with Home. Dedicated buyer, seller and admin browser journeys passed. The synthetic admin photo-key fixture and mocked Paystack flow do not verify live R2/Paystack operations.

Remaining architecture work: ChatDetail/Chats (E2EE/realtime), DocumentStudy/Reader (offline/progress), generation flows, Home/Explore and app-shell orchestration; backend route/service/model extraction from the global Flask module. Keep each slice test-first, prop-driven and behavior-preserving. The populated-database migration/backup-restore rehearsal must be repeated through Alembic head 20261030_shared_study_streak. The overall release remains blocked by provider, retrieval/backfill/citation, monitoring/request-ID and B2B viewability gates. The exact CI evidence above is pre-merge code-head evidence; no separate post-merge CI run is claimed.

## 2026-11-12 — current-main architecture reconciliation

Current main is documentation-only commit `09bd1d82910d83797da2303a9f42afbd1739fbfe`; the runtime code snapshot remains `0f393bd011d6047915cbb12a15acac87f21102c0`. The verified source sizes remain `frontend/src/App.tsx` at 5,034 lines and `app.py` at 9,643 lines. The Admin boundary is complete as a structural extraction: `AdminSection.tsx` is a 172-line dispatcher, `useAdminSectionController.ts` owns the 934-line state/effect/API controller, the core/platform render-only views are 783/368 lines, and the growth/domain panels are 531/728 lines. The controller stays unconditional so section changes preserve its state/effect lifetime. Podcast Player is module-owned at 349 lines. These are ownership improvements, not a claim that the whole frontend/backend refactor is complete.

The current route switch was checked before choosing the next screen boundary:

- `home` mounts `HomeScreen`; `explore` mounts `ExploreScreen`.
- `chats` mounts `WhatsAppChatExperience`, not the old inline `ChatsScreen` declaration.
- `document-study` mounts `DocumentStudyHubScreen`, not the old inline `DocumentStudyScreen` declaration.
- `document-reader` mounts the still-inline `DocumentReaderScreen`; it owns offline Blob opening, page progress persistence, study-time heartbeat and native page rendering.
- `chat-detail` mounts the still-inline `ChatDetailScreen`; its E2EE/realtime coupling requires a separate dependency map.

Therefore, do not spend an extraction slice moving the unmounted legacy `ChatsScreen` or `DocumentStudyScreen` just to lower `App.tsx` line count. The next safe frontend slice is the active `DocumentReaderScreen`, but only after making every source-transform dependency module-aware. Current transforms/scripts still locate or rewrite that declaration in `App.tsx` (including document-reader insertion, reading-progress and navigation-polish transforms); update those paths and add idempotency/preservation tests before moving the component. Preserve the offline Blob, page-progress, heartbeat, authorization, page URL and back-navigation contracts exactly. Then map `ChatDetailScreen` dependencies before attempting its extraction.

The current-main Frontend Build [43171345722](https://github.com/apexstudying-cmd/prepza/actions/runs/43171345722), Release Browser [43171345717](https://github.com/apexstudying-cmd/prepza/actions/runs/43171345717), and Release QA Trace [43171345768](https://github.com/apexstudying-cmd/prepza/actions/runs/43171345768) passed. The populated-database migration and backup/restore rehearsal passed in [run 43171200015](https://github.com/apexstudying-cmd/prepza/actions/runs/43171200015) on adjacent code SHA `73276018786bdaf007396c514fa0f358145138a7`; the final combined one-SHA release regression remains open.

## 2026-11-13 — current consolidated architecture candidate (supersedes the earlier inline-screen checkpoint)

The earlier route-switch note above is historical. On candidate `0c29859b3eb3b7acf3593e97eb9d08c57ac96acc` in [PR #79](https://github.com/apexstudying-cmd/prepza/pull/79), active DocumentReader and ChatDetail are feature-owned modules. Home, Explore, generated-study screens, AppShell, BottomNav and the navigation hook are module-owned. AdminSection/controller/views were already on main. Alternate ChatDetail PR #80 was closed to keep one integration review.

Verified sizes: `frontend/src/App.tsx` 3,051 lines; `app.py` 8,791; `AdminSection.tsx` 172; `useAdminSectionController.ts` 934; `DocumentReaderScreen.tsx` 243; `ChatDetailScreen.tsx` 582; `AppShell.tsx` 62; `BottomNav.tsx` 56; `useAppNavigation.ts` 57. This is progress, not completion or a requirement that every file be below 1,000 lines.

Remaining active inline frontend screens include Upload, UploadShareChoice, Processing, PublishLibrary and Subscription/Payment flows. The old inline ChatsScreen and DocumentStudyScreen declarations are unmounted and must not be extracted solely to lower line count. Backend `app.py` still contains large document/generation, Library, groups, follows, notifications, content, subscription/ambassador, base-chat and audit route groups. Continue by mapping dependencies, adding focused contracts first, moving one active boundary at a time, and preserving registration order, authorization, response shapes and transaction behavior.

Frontend Build [43389767091](https://github.com/apexstudying-cmd/prepza/actions/runs/43389767091), Backend Shared Extension [43389767160](https://github.com/apexstudying-cmd/prepza/actions/runs/43389767160) and Release Browser [43389767185](https://github.com/apexstudying-cmd/prepza/actions/runs/43389767185) passed on exact candidate SHA. StudyHub Library Flow [43389767147](https://github.com/apexstudying-cmd/prepza/actions/runs/43389767147) was SKIPPED. PR #79 remains draft while remaining active screen/backend boundaries are unfinished.

## 14 November 2026 — consolidated candidate verification and remaining boundaries

The single integration PR [#79](https://github.com/apexstudying-cmd/prepza/pull/79) is still draft at head `edcfad751e4f3774e297219ecbb4c22cc31ef854` (123 commits ahead and 2 behind current main `02fcdfb12ab065d6613b08bd82d031cc3bb109ea`). Frontend Build [43566535402](https://github.com/apexstudying-cmd/prepza/actions/runs/43566535402), Release Browser [43566535290](https://github.com/apexstudying-cmd/prepza/actions/runs/43566535290) and PostgreSQL Backup Restore [43566535421](https://github.com/apexstudying-cmd/prepza/actions/runs/43566535421) all passed on the same exact candidate. The branch is not merged; remaining boundaries and release gates still require work.

The candidate owns active DocumentReader, ChatDetail, Home, Explore, generated-study screens and AppShell/navigation modules. AdminSection remains a 172-line dispatcher with the unconditional controller and render-only core/platform views already split. Current `App.tsx` is 3,051 lines and `app.py` is 8,791 lines; these are not launch criteria by themselves.

The next safe frontend slice is the connected active `UploadScreen`, `UploadShareChoiceScreen` and `ProcessingScreen` flow. Before extraction, inventory every source-transform dependency and prop/state/API contract, add idempotency and behavior-preservation tests, then move the existing implementation without changing upload validation, document ownership, processing state, navigation or API behavior. Follow with `PublishLibraryScreen` and Subscription/Payment boundaries. Then map backend document/library/group/follow/notification/subscription/base-chat route groups and extract one tested boundary at a time. Do not move unmounted legacy `ChatsScreen` or `DocumentStudyScreen` declarations solely to reduce line count.
