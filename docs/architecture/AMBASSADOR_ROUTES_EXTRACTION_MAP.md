# Ambassador student-route extraction map

Status: the seven student-facing ambassador routes are verified on exact application-code head `7d12cbfebbc2bf48f501cb25ad2f3d979aae4631` in PR #79. The admin Paystack transfer helpers are a separate unresolved service contract and are not covered by this student-route extraction.

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

The extraction is verified on exact code head `7d12cbfebbc2bf48f501cb25ad2f3d979aae4631`: Backend Shared Extension Contract [44475284636](https://github.com/apexstudying-cmd/prepza/actions/runs/44475284636) PASS (96 tests); Frontend Build [44475284756](https://github.com/apexstudying-cmd/prepza/actions/runs/44475284756) PASS (192 source/module + 5 offline Library tests); Release Browser [44475284585](https://github.com/apexstudying-cmd/prepza/actions/runs/44475284585) PASS (101 PostgreSQL QA tests, Shop and B2B browser journeys); PostgreSQL Backup Restore [44475284651](https://github.com/apexstudying-cmd/prepza/actions/runs/44475284651) PASS. The student-facing route extraction does not verify the separate Paystack transfer service: `_apply_paystack_transfer_result`, `initiate_paystack_transfer` and `sync_paystack_transfer_status` remain unresolved references. No live provider transfer was attempted.
