# Ambassador student-route extraction map

Status: implementation added to PR #79; exact-head verification pending.

## Scope

Move only the seven student-facing HTTP handlers from the Flask composition module into `ambassador_routes.py`:

| Endpoint | Method | Existing handler |
|---|---|---|
| `/ambassador/apply` | POST | `ambassador_apply` |
| `/ambassador/status` | GET | `ambassador_status` |
| `/ambassador/dashboard` | GET | `ambassador_dashboard` |
| `/ambassador/referral-qr` | GET | `ambassador_referral_qr` |
| `/ambassador/referrals` | GET | `ambassador_referrals` |
| `/ambassador/payouts` | GET | `ambassador_payouts` |
| `/ambassador/payouts/request` | POST | `ambassador_request_payout` |

## Dependency ownership

- `Ambassador`, `Referral` and `AmbassadorPayout` remain owned by `opportunity_models.py`.
- `get_ambassador_settings`, `compute_ambassador_tier` and `generate_referral_code` remain in `app.py`: signup/profile and first-payment/referral lifecycle code also calls these helpers.
- The new route module receives the database, models, limiter, CSRF decorator, base URL and helper callables explicitly. It does not import `app.py`.
- The referral serializer, unique-code retry helper and payout-destination validation constant move with the HTTP handlers.

## Preservation requirements

- Keep registration at the same startup position: after notification-preference routes and before opportunity routes.
- Keep endpoint names, URL paths, methods, response shapes, session checks, pagination, status rules and database predicates.
- Keep the existing 5-per-hour limiter and CSRF decorator on application and payout-request POST routes.
- Preserve payout creation order: add payout, flush for its generated ID, assign that ID to each eligible unlocked/non-voided/unpaid referral, commit once, and return the created response.
- No ambassador frontend UI, commission settings, payout eligibility, provider behavior or database schema changes are part of this extraction.

## Regression coverage

- `tests/test_backend_route_registry_contract.py` verifies module ownership, registration order, all seven endpoint/method mappings, and the two rate-limit/CSRF pairs.
- `tests/test_local_qa_real_world.py::test_ambassador_payout_request_persists_bundle_and_rejects_duplicates` continues to exercise the real disposable database route, recipient fields, payout amount, referral payout-ID assignment and duplicate-request rejection.
- Backend Shared Extension Contract compiles `ambassador_routes.py` and runs the registry contract suite.

## Verification

The previous exact candidate `b24d583f054f056161c714a15d558406672acb4d` passed Frontend Build [43686512095](https://github.com/apexstudying-cmd/prepza/actions/runs/43686512095), Release Browser [43686511971](https://github.com/apexstudying-cmd/prepza/actions/runs/43686511971) and PostgreSQL Backup Restore [43686511937](https://github.com/apexstudying-cmd/prepza/actions/runs/43686511937). Those results predate this route move.

The current extraction is **NOT_TESTED** until Backend Shared Extension Contract, Frontend Build, Release Browser and PostgreSQL Backup Restore finish on the new exact PR head.
