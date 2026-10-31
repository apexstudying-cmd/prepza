# Prepza frontend engineering guide

Prepza's frontend is a React 19 + TypeScript application built with Vite 8 and Tailwind CSS v4. This guide describes the actual repository, not an assumed hosted preview environment.

## Local development

The development server is **not assumed to be running**. From the repository root:

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm dev
```

Vite listens on `0.0.0.0` and defaults to port `8443` (override with `PORT`). Its development proxy sends API requests to `http://127.0.0.1:5000` by default; set `VITE_API_PROXY_TARGET` if Flask runs elsewhere.

## Build and verification

From `frontend/`:

```bash
pnpm build
```

The build command runs a long `prebuild` chain of Python source-transform scripts, then TypeScript and Vite, followed by repository architecture audits. Use the checked-in command rather than invoking `vite build` directly when validating a production build.

The prebuild chain requires Python 3 and the dependencies used by the repository scripts. CI currently uses Python 3.13. Source transforms can edit files under `src/`; inspect their target and add a regression test before changing one. A successful TypeScript check alone is not enough to prove the transformed app preserves all route components.

Focused frontend source-transform tests are run in CI from the repository root:

```bash
python -m pytest -q \
  tests/test_generation_ui_build_contract.py \
  tests/test_frontend_module_extraction_contract.py \
  tests/test_document_study_progress_transform.py \
  tests/test_frontend_ambassador_module_contract.py
```

## Entry points and ownership

- `src/main.tsx` - React entrypoint; imports global CSS and mounts the app.
- `src/App.tsx` - legacy application shell, screen routing/composition, and screens still awaiting extraction. Keep it as the integration point; avoid adding new feature implementations here when a focused module is practical.
- `src/lib/appApi.ts` - shared application JSON API helper and `ApiError`. Preserve cookie credentials, JSON handling, and error semantics.
- `src/lib/api.ts` - separate chat-oriented API client with its own CSRF/current-user state. Do not merge it with `appApi.ts` without a dedicated contract migration.
- `src/theme/theme.ts` - shared Prepza palette and light/dark theme store.
- `src/ui/icons.tsx` - shared icon primitives.
- `src/types/academic.ts` - university and program option contracts.
- `src/screens/onboarding/CompleteProfileScreen.tsx` - academic profile-completion flow.
- `src/screens/ambassador/AmbassadorScreen.tsx` - ambassador application, dashboard, referral, and payout-request UI.
- `src/screens/settings/SettingsScreen.tsx` - account settings, privacy, notification preferences, appearance, security, logout, and account deletion.
- `src/ui/Pill.tsx` - shared status pill component.
- `src/lib/pushNotifications.ts` - browser push subscription/unsubscription helpers using the shared application API client.
- `src/screens/<domain>/` - home for additional screen-level compositions, grouped by feature domain.
- `src/admin/`, `src/crypto/`, `src/generation/`, `src/offline/`, `src/organisation/`, and `src/share/` - existing feature modules. Retain their boundaries unless a dependency map supports a safe move.

## Dependencies and styling

- Runtime: React 19 and React DOM 19.
- Styling: Tailwind CSS v4 through `@tailwindcss/vite`; global styles are in `src/index.css`.
- Build: Vite 8, TypeScript 5.7, and `@vitejs/plugin-react`.
- Formatting: `oxfmt`.

## Refactor rules

1. Keep `App.tsx` as the integration point while extracting one feature at a time.
2. Move existing behavior verbatim first; do not combine extraction with UX, API, or business-rule changes.
3. Pass navigation callbacks and domain data explicitly. Never import the App module from a screen module.
4. Add a behavior/contract test before moving logic, then run the focused test, TypeScript check, and production build.
5. Do not remove `// @ts-nocheck` from the legacy App file as a blanket change. Remove it only after affected code has proper types and relevant tests pass.
6. Build-time source transforms must preserve unrelated component declarations and route targets. Add regression coverage for each transform that edits `App.tsx`.
7. Keep the application API client and chat API client separate until their authentication, CSRF, cache, and error contracts are deliberately reconciled.
