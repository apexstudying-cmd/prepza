# Admin frontend ownership

The admin feature is entered through `AdminPlatform`, imported by the app shell. Keep the existing route IDs, section keys, server endpoints, authorization checks, and CSRF behavior unchanged when restructuring it.

## Module map

- `AdminPlatform.tsx` — compact platform shell: sidebar navigation, section labels, header, and the existing `AdminPlatform` entry point. It also exports the payment-status display metadata consumed by the student payment-history screen.
- `AdminSection.tsx` — small section dispatcher. It preserves the existing settings view and routes the other sections to their view modules.
- `useAdminSectionController.ts` — owns admin state, effects, API calls, CSRF handling, loading/error state, and mutation handlers. The hook is called unconditionally by `AdminSection`, preserving state/effect lifetime across tab changes.
- `AdminSectionCoreViews.tsx` — typed, render-only dashboard, users, Library/content, AI usage, payments, moderation, and analytics views.
- `AdminSectionPlatformViews.tsx` — typed, render-only infrastructure/system and communications views.
- `AdminPanels.tsx` — independent domain panels for ambassadors, opportunities, promotions, organisations, groups, universities, and community reports.
- `AdminShared.tsx` — shared admin response types and presentational primitives (`AdminCard`, `AdminKPI`, `AdminTable`, charts, and badges).
- `B2BFinanceAdmin.tsx` and `AdminOperationsDashboard.tsx` — existing dedicated finance and operations modules.

## Change-safety rules

1. Treat the server as the authority for admin permissions. A hidden tab or UI check is not authorization.
2. Preserve existing API paths, HTTP methods, request/response shapes, CSRF headers, loading/error states, confirmation prompts, and mutation ordering.
3. Keep navigation keys stable; the sidebar and section renderer share these keys.
4. Prefer explicit props and feature-owned types when extracting a tab. Do not import `App.tsx` from an admin module.
5. Do not disable or bypass prebuild transformers. Some admin tooling patches the settings UI; its target is now `AdminSection.tsx`.

## Verification

From the repository root:

```bash
python -m pytest -q tests/test_generation_ui_build_contract.py
pnpm --dir frontend build
```

The Frontend Build workflow also runs source-transform contracts, offline Library regression, TypeScript, service-worker validation, production Vite build, and architecture/launch-wiring audits. The Admin Route Contract separately protects backend admin route behavior.

## Admin section state/view boundary

The main admin section is split between one stateful controller and bounded render modules. View components receive a typed `Pick<AdminSectionController, ...>` rather than importing API clients or owning new effects. Keep network calls, authorization-related UI state, CSRF headers, confirmation flows and mutation ordering in the controller; keep JSX and display-only derived values in the view modules. This preserves the existing section IDs and avoids resetting parent-owned state when users switch tabs.

Current extraction target sizes are kept below 1,000 lines per file: `AdminSection.tsx` is the dispatcher, `useAdminSectionController.ts` is the controller, and the two view modules are separate domain groups. Do not split the controller further until its effects and mutation dependencies have focused contract coverage.
