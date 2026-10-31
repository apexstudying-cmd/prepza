# Prepza repository architecture and safe refactor plan

**Purpose:** make the repository easier to navigate and maintain without changing user-visible behavior, API contracts, authorization, persistence, billing, or product rules.

**Baseline source checkpoint:** `f747b0d95a6b81cb2868843093546a97e3d09fb5` (2026-10-31).
**Working branch:** `refactor/architecture-foundation`.
**Status:** incremental refactor in progress. This document distinguishes current implementation from target structure.

## 1. Verified baseline

The initial source scan found:

| Area | Baseline size | Observation |
|---|---:|---|
| `app.py` | 10,332 lines; 318 top-level function/class declarations | Flask setup, SQLAlchemy models, shared helpers, and many HTTP routes coexist in one module. |
| `frontend/src/App.tsx` | 16,032 lines; 154 declarations at the initial scan. After the first extraction: 15,747 lines; 149 declarations. | The first extraction moved shared API/theme/icon/type definitions and the academic profile-completion screen into focused modules. Many screens still remain in the composition file. |
| Frontend build | Long `prebuild` chain | Python scripts rewrite source files before TypeScript/Vite compilation. |
| Local QA runner | 11 listed test files | `docs/qa/actualtest.md` describes an older suite inventory and contains inconsistent counts; it must be reconciled against the exact latest run. |

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

### Frontend largest remaining screen areas

The current `App.tsx` scan shows these large declarations still embedded in the app shell:

| Declaration | Approximate lines | Refactor priority |
|---|---:|---|
| `AdminSection` | 1,961 | High; split by admin domain after mapping state and permissions |
| `readStoredNavigationState` and adjacent navigation persistence block | 538 | High; move pure navigation persistence to `app/navigation/` with storage-contract tests |
| `GroupDetailScreen` | 418 | Medium; extract group detail UI and explicit callbacks |
| `ChatDetailScreen` | 406 | High; extract only after mapping E2EE, realtime and message-state dependencies |
| `SettingsScreen` | 374 | Medium; extract with typed settings/account callbacks |
| `AmbassadorScreen` | 367 | Medium; extract as a self-contained business feature |
| `ChatsScreen` | 358 | High; extract after mapping realtime and encryption integration |
| `ChatOptionsScreen` | 331 | Medium |
| `PodcastPlayerScreen` | 327 | Medium |
| `DocumentStudyScreen` | 323 | High; protect reader progress/offline contracts |
| `LibraryScreen` | 305 | Medium |
| `SignupScreen` | 251 | Medium; keep auth, CSRF and navigation behavior unchanged |

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

The architecture branch has extracted the following existing implementations without intentionally changing their behavior:

| New module | Responsibility |
|---|---|
| `frontend/src/lib/appApi.ts` | The existing App-level cookie-authenticated JSON fetch helper and `ApiError`. |
| `frontend/src/theme/theme.ts` | Existing brand palette and shared light/dark theme store. |
| `frontend/src/ui/icons.tsx` | Existing shared `Ic` icon map. |
| `frontend/src/types/academic.ts` | Shared university and program option types. |
| `frontend/src/screens/onboarding/CompleteProfileScreen.tsx` | Existing academic-profile completion screen. |

`App.tsx` imports these modules and retains the application-level navigation integration. The legacy `frontend/src/lib/api.ts` remains separate: it has a different chat-oriented API and CSRF state contract. These two clients must not be merged until their behavioral differences are understood and tested.

The first extraction reduced `App.tsx` from 16,032 to approximately 15,747 lines. This is an initial boundary improvement, not completion of the frontend refactor.

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
- [ ] Complete full CI and browser verification for the current extraction.
- [ ] Reconcile QA documentation against the exact current runner and test output.
- [ ] Continue frontend screen extraction in small, dependency-mapped slices.
- [ ] Design and implement backend app-factory/extensions boundaries with compatibility tests.
- [ ] Extract backend route/service domains incrementally.
- [ ] Reduce and eventually retire build-time source mutation after every transform has a committed source equivalent.
