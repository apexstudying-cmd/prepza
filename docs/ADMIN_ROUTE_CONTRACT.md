# Admin route contract — Day 3

Date: 2026-09-30
Branch: `main`

This is the authoritative source-level reconciliation record for the admin UI/backend audit.

## Result

The old `chunk10_*.patch` files were **not** identical to the current `main`. They were older snapshots of work that is partly already present and partly absent.

The current `app.py` already contains several Chunk 10 data models and some related admin functionality, while the corresponding route implementations are missing from the current backend. The frontend still calls those routes.

The reconciliation therefore restores the missing **compatible route layer** rather than replacing current `app.py` with historical patches.

## Restored contract families

- Communications: `/admin/announcements`
- AI usage: `/admin/ai-usage`
- Moderation: `/content-reports`, `/admin/content-reports/*`, `/warnings`
- University/program administration: `/admin/universities/*`, `/admin/programs/*`
- Community group administration: `/admin/groups/*`
- Student opportunities: `/opportunities/*`, `/admin/opportunities/*`

## Important compatibility choices

- Existing current models are reused. No duplicate model definitions are introduced.
- Existing `require_admin` and `require_csrf` guards are preserved.
- Existing current student/group/opportunity serializers and lifecycle helpers are reused where possible.
- Historical patches are treated as implementation references, not as authoritative current source.
- Payment, ambassador, settings, analytics, and capacity routes that the UI references but that are not represented by the Chunk 10 patches remain a separate reconciliation item. They must be implemented from their current frontend contracts and current models/modules rather than guessed from stale code.
- No database migration is invented in this pass. The restored routes rely on models/tables already represented by the current source/migration inventory; schema verification remains a deployment-stage requirement.

## Regression guard

Day 3 also adds a static admin route-contract audit. It compares literal frontend admin API paths with the backend route registry and reports missing backend paths. This is intended to catch future frontend/backend drift in CI.

## Deployment boundary

This work is code-level reconciliation only. Render production is still untouched, the VPS remains paused, and no production database is migrated.
