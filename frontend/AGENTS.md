# figma-make-app

React + Vite + Tailwind CSS project running inside Figma Make.

## Development Server

A Vite development server is **already running** on `$PORT` (default 8443). You don't need to start it manually.

- Preview URL: The user can access the running app through the preview panel
- Hot reload: Changes to source files are reflected immediately

## Project Structure

This is the canonical project structure. Start with task-relevant files below. Only follow imports or inspect other files when required, when a documented path is missing, or when the repository contradicts this guide.

- `src/main.tsx` - React entrypoint; imports `src/index.css` and mounts `src/App.tsx` into the `#root` element
- `src/App.tsx` - Primary application component and the usual starting point for UI work
- `src/index.css` - Global CSS entrypoint and Tailwind CSS v4 import
- `index.html` - Vite HTML shell containing the `#root` element and loading `src/main.tsx`
- `package.json` - Project dependencies and the Vite build, development, preview, and formatting scripts
- `vite.config.ts` - Vite configuration with React, Tailwind CSS v4, and Figma Make plugins plus the `@` alias for `src`
- `.mise.toml` - Toolchain versions for Node.js and pnpm

## Dependencies

- Runtime: React 19 and React DOM 19
- Styling: Tailwind CSS v4 with the `@tailwindcss/vite` plugin
- Build tooling: Vite 8, TypeScript 5.7, and `@vitejs/plugin-react`
- Formatting: oxfmt

## Styling

This project uses **Tailwind CSS v4** through the `@tailwindcss/vite` plugin configured in `vite.config.ts`. `src/index.css` imports Tailwind with `@import 'tailwindcss';`. Use Tailwind utility classes directly in JSX and put global CSS or Tailwind v4 theme customization in `src/index.css`. This scaffold does not need a Tailwind config file or PostCSS config.

`src/main.tsx` imports `src/index.css`, so global font wiring belongs in `src/index.css`. Keep CSS `@import` statements first, then add any `@font-face` rules and font-family defaults there.

## Code quality

- Use double quotes for strings containing apostrophes (`"We're here to help"`), or escape them in single-quoted strings. An unescaped apostrophe in a single-quoted string breaks the build.
- Ensure JSX tags are closed and braces are balanced.
- Export components as default exports.


## Prepza feature organization

The frontend is being modularized incrementally. Prefer these ownership boundaries for new work:

- `src/App.tsx` - legacy application shell, route selection, and remaining screens. Keep new feature implementation out of this file where a focused module is practical.
- `src/lib/appApi.ts` - shared application JSON API helper and `ApiError`. Preserve cookie credentials, JSON handling, and existing error semantics.
- `src/lib/api.ts` - separate chat-oriented API client with its own CSRF/current-user state. Do not merge it with `appApi.ts` without a dedicated contract migration.
- `src/theme/theme.ts` - shared Prepza brand palette and light/dark theme store.
- `src/ui/icons.tsx` - shared icon primitives.
- `src/types/academic.ts` - university and program option contracts.
- `src/screens/<domain>/` - screen-level compositions, grouped by feature domain.
- `src/admin/`, `src/crypto/`, `src/generation/`, `src/offline/`, `src/organisation/`, and `src/share/` - existing feature modules; retain their current boundaries unless a specific dependency map supports a safe move.

### Refactor rules

1. Keep `App.tsx` as the integration point while extracting one feature at a time.
2. Move existing behavior verbatim first; do not combine extraction with UX, API, or business-rule changes.
3. Pass navigation callbacks and domain data explicitly. Avoid importing the App module from a screen module.
4. Add a behavior/contract test before moving logic, then run the focused test, TypeScript check, and production build.
5. Do not remove `// @ts-nocheck` from the legacy App file as a blanket change. Remove it only after the affected code has proper types and its relevant tests pass.
6. Build-time source transforms must preserve unrelated component declarations and route targets. Add regression coverage for each transformation that edits `App.tsx`.
