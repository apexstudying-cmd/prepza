# Prepza — Actual QA Test Record

This file is the authoritative human-readable record of the **full local QA suite** run by `tools/run_local_qa.py`.

It answers four questions exactly:

1. How many tests are in the full suite?
2. How many test users/roles does the suite create?
3. Which test files are included?
4. What does every test actually verify?

## 1. Exact suite size

The full QA runner currently executes **10 test files**.

Those files contain:

- **72 test functions** named `test_...`
- **75 collected pytest test cases**
- The difference is caused by one parametrized test:
  - `test_generation_request_ceilings_are_enforced` runs for **4 material types**: summary, podcast, flashcards, and mind map.
  - Therefore that one function contributes 4 collected cases instead of 1.
  - 71 functions + 3 extra parameter cases = **74 collected cases**.

The latest successful full run proved:

**74 passed, 0 failed, 3375 warnings.**

Warnings are not failed tests. The current warnings are primarily technical-debt warnings such as deprecated `datetime.utcnow()` usage and a legacy SQLAlchemy `Query.get()` usage.

## 2. Exact QA users and roles

The disposable QA world is created in `tests/test_local_qa_real_world.py` and reused by the related QA modules.

### Seven distinct QA user accounts are created across the full suite

| User | Role / purpose | Main coverage |
|---|---|---|
| `qa.student.a@test.invalid` | Student; Organisation A owner | Main authenticated student, organisation owner, opportunity lifecycle, realtime sender |
| `qa.student.b@test.invalid` | Student; Organisation B owner in authz tests | Second student, outsider/tenant-boundary checks, realtime receiver |
| `qa.admin@test.invalid` | Administrator | Admin queue, organisation verification, admin authorization |
| `qa.student.c@test.invalid` | Student | Targeting matrix; different year/profile |
| `qa.student.d@test.invalid` | Student | Targeting matrix; different program/semester/profile |
| `qa.economics@test.invalid` | Student | Free/Plus/Pro entitlement and quota lifecycle |
| `qa.paystack@test.invalid` | Student | Paystack plan price/currency/idempotency contract |

### Role count

- **6 student accounts**
- **1 admin account**
- **7 distinct user accounts total**

There are also **2 disposable organisations** used by the authorization tests:

- Organisation A — owned by student A
- Organisation B — created and owned by student B

The word "owner" here is an **organisation membership role**, not a separate User role. The admin account has `is_admin=True`.

### Important distinction

The suite does **not** simulate seven real people connecting at once.

These are controlled test identities used to exercise different authorization, entitlement, targeting, realtime, and concurrency scenarios. Some tests use two users together; the realtime/E2EE fixture uses student A, student B, and the admin as an outsider.

The production-style focused scripts (`scripts/test_realtime_runtime.py` and `scripts/test_calling_runtime.py`) are separate from this 74-case disposable QA suite and currently use their own runtime test setup.

## 3. How the full QA environment is built

`tools/run_local_qa.py`:

1. Requires a real `DATABASE_URL`.
2. Refuses to bootstrap QA from an existing database whose name is already `prepza_qa` or ends in `_qa`.
3. Creates/uses the disposable PostgreSQL database `prepza_qa`.
4. Runs `alembic upgrade head`.
5. Runs the 10 test files below with pytest.
6. Sets `REDIS_URL=memory://` for the disposable suite so rate-limit counters and Socket.IO test behavior are isolated from the running production-style Redis service.
7. Retains the QA database after the run so failures can be inspected.

This is deliberate: the suite tests the real Flask application and PostgreSQL schema, while avoiding accidental changes to the normal application database.

## 4. Exact test files and test functions

### A. `tests/test_local_qa_real_world.py` — 15 test functions

This is the broadest end-to-end route and business-behavior layer.

1. **`test_route_inventory_contains_critical_boundaries`**
   - Verifies critical routes are actually registered.
   - Checks important student/admin/opportunity boundaries.
   - Detects dangerous duplicate student-facing route registrations.

2. **`test_no_duplicate_registered_route_methods`**
   - Scans Flask's final URL map.
   - Fails if the same route/method is registered by multiple endpoints.

3. **`test_public_and_authenticated_session_boundaries`**
   - Verifies public health access.
   - Verifies anonymous users cannot access `/me`.
   - Verifies an authenticated student can access `/me`.
   - Verifies logout invalidates the session.

4. **`test_university_and_program_lookup_are_real_routes`**
   - Exercises university and program lookup through real HTTP routes.

5. **`test_group_creation_is_end_to_end`**
   - Creates a study group through the real route.
   - Verifies listing and detail retrieval.

6. **`test_organisation_opportunity_lifecycle_and_targeting`**
   - Exercises organisation opportunity creation.
   - Applies targeting.
   - Verifies invalid early submission is blocked.
   - Verifies admin organisation verification.
   - Verifies submission, admin queue visibility, approval, publishing, student visibility, and outsider hiding.

7. **`test_organisation_can_create_multiple_opportunities_under_live_rate_limit`**
   - Re-enables the real rate limiter.
   - Proves a legitimate organisation can create five opportunities without the limiter incorrectly blocking normal activity.

8. **`test_opportunity_targeting_matrix_and_current_profile_changes`**
   - Creates additional student profiles with deliberately different university/program/year/semester values.
   - Exercises targeting combinations.
   - Verifies profile changes affect targeting correctly.

9. **`test_student_economics_entitlement_lifecycle_and_quota_truth`**
   - Tests Free/Plus/Pro entitlement activation and expiry.
   - Verifies payment success alone does not incorrectly activate a plan before fulfillment.
   - Checks additive entitlements and exact remaining AI quota.
   - Checks per-request ceilings and expiry/future-start boundaries.

10. **`test_paystack_checkout_uses_base_plan_price_and_provider_success_is_idempotent`**
    - Verifies checkout uses the canonical plan price.
    - Verifies KES/monthly provider contract.
    - Verifies provider success synchronization is idempotent.

11. **`test_csrf_and_session_version_fail_closed`**
    - Verifies state-changing requests fail safely without the correct CSRF/session contract.

12. **`test_duplicate_opportunity_save_is_race_safe`**
    - Exercises concurrent duplicate-save behavior.
    - Verifies the operation does not create an unsafe duplicate state.

13. **`test_concurrent_organisation_reads`**
    - Exercises concurrent organisation reads to expose unsafe request/database behavior.

14. **`test_every_registered_route_dispatches_without_server_error`**
    - Walks the registered route surface with representative requests.
    - Detects routes that exist statically but fail when actually dispatched.

15. **`test_b2b_prepaid_metering_protects_advertiser_balance_and_locks_campaign_pricing`**
    - Verifies prepaid balance protection.
    - Verifies billable-event pricing is locked to campaign economics.
    - Exercises B2B metering behavior against advertiser balance.

### B. `tests/test_route_security_matrix.py` — 3 test functions

16. **`test_every_admin_get_route_rejects_anonymous_and_non_admin_users`**
    - Enumerates admin GET routes.
    - Verifies anonymous users and ordinary students cannot access them.

17. **`test_every_admin_mutation_fails_without_csrf_for_all_non_admins_and_admin`**
    - Enumerates admin state-changing routes.
    - Verifies missing/invalid CSRF protection is rejected for the security boundary.

18. **`test_revoked_admin_cannot_continue_using_existing_session`**
    - Logs an admin into an existing session, revokes `is_admin` in the live database row, and verifies the same session is immediately denied with 403.
    - Restores the fixture's admin flag during cleanup.

### C. `tests/test_authenticated_route_matrix.py` — 1 test function

19. **`test_every_get_route_dispatches_for_authenticated_student_and_admin`**
    - Exercises the GET route surface with authenticated student and admin identities.
    - Detects routes that look registered but fail at runtime.

### D. `tests/test_local_qa_authz.py` — 5 test functions

20. **`test_student_cannot_cross_organisation_boundary`**
    - Creates a second organisation.
    - Verifies one student cannot use another tenant's IDs to create or mutate resources.
    - This is an IDOR/horizontal authorization check.

21. **`test_student_cannot_cross_vertical_admin_boundary`**
    - Verifies an ordinary student cannot perform administrator-only operations.

22. **`test_logout_and_session_version_rotation_invalidate_old_session`**
    - Verifies logout and session-version rotation invalidate an old authenticated session.

23. **`test_suspended_account_cannot_continue_using_existing_session`**
    - Suspends an account.
    - Verifies an existing authenticated session no longer grants access.

24. **`test_state_changing_organisation_actions_require_csrf`**
    - Verifies organisation mutations require the expected CSRF token.

### E. `tests/test_frontend_ai_generation_contract.py` — 3 test functions

25. **`test_backend_generation_routes_and_payload_keys_match_contract`**
    - Verifies backend generation endpoints and response payload names match the expected contract.

26. **`test_active_frontend_generation_contract_matches_backend`**
    - Compares active frontend generation calls with backend route/payload expectations.
    - Catches frontend/backend naming drift.

27. **`test_frontend_usage_contract_uses_canonical_usage_endpoint`**
    - Verifies the frontend uses the canonical usage endpoint.

### F. `tests/test_ai_artifact_fingerprint.py` — 10 test functions

28. **`test_shared_identity_is_deterministic`**
    - Same generation identity inputs produce the same fingerprint.

29. **`test_parameter_order_does_not_change_identity`**
    - Reordering equivalent parameters does not create a different artifact identity.

30. **`test_parameters_change_identity`**
    - Meaningful generation parameter changes create a different identity.

31. **`test_prompt_and_schema_versions_change_identity`**
    - Prompt/schema version changes invalidate the old artifact identity.

32. **`test_shared_and_private_scopes_never_collide`**
    - Shared and private generation scopes cannot accidentally share identities.

33. **`test_private_identity_is_owner_specific`**
    - Private artifact identity includes the correct owner boundary.

34. **`test_scope_is_normalized`**
    - Scope values are normalized consistently.

35. **`test_private_requires_owner`**
    - Private generation cannot be created without an owner.

36. **`test_shared_rejects_owner`**
    - Shared generation cannot incorrectly carry a private owner identity.

37. **`test_invalid_scope_is_rejected`**
    - Unknown generation scopes are rejected.

### G. `tests/test_ai_generation_store.py` — 2 test functions

38. **`test_generation_lookup_shapes_are_explicit`**
    - Verifies generation lookup states have an explicit, usable shape.

39. **`test_only_owner_is_allowed_to_call_provider`**
    - Verifies only the generation owner/producer can reach the provider path.

### H. `tests/test_ai_economics.py` — 12 test functions

40. **`test_ada_unit_weights_are_locked`**    - Locks the canonical Ada AI unit weights.

41. **`test_ada_units_round_up`**
    - Verifies AI unit calculations round up according to the economic contract.

42. **`test_plan_defaults_match_locked_entitlements`**
    - Verifies Free/Plus/Pro default limits match the locked product economics.

43. **`test_plan_patch_rejects_unknown_fields`**
    - Rejects unsupported plan fields.

44. **`test_plan_patch_rejects_negative_limits`**
    - Rejects negative quota/limit values.

45. **`test_plan_patch_accepts_feature_and_access_flags`**
    - Verifies valid feature/access flags can be patched.

46. **`test_offline_study_is_core_for_free`**
    - Verifies offline study is part of the Free entitlement.

47. **`test_admin_cannot_disable_offline_study`**
    - Protects the product contract from disabling the core offline feature.

48. **`test_paystack_plan_sync_updates_provider_when_price_drifts`**
    - Verifies provider plans are updated when the provider price is wrong.

49. **`test_paystack_plan_sync_does_not_write_when_already_matching`**
    - Verifies no unnecessary provider write occurs when the plan already matches.

50. **`test_paystack_plan_sync_requires_plan_code`**
    - Rejects provider synchronization without the required plan code.

51. **`test_student_offer_definition_is_monthly_and_plan_isolated`**
    - Verifies the student offer is monthly and plan-specific.

### I. `tests/test_ai_reusable_generation.py` — 13 test functions

52. **`test_normalize_parameters_is_deterministic_and_whitespace_safe`**
    - Canonicalizes generation parameters deterministically.

53. **`test_normalize_parameters_rejects_unknown_keys`**
    - Rejects unsupported generation parameters.

54. **`test_normalize_parameters_rejects_invalid_counts`**
    - Rejects invalid generation counts.

55. **`test_normalize_parameters_rejects_blank_strings`**
    - Rejects meaningless blank generation parameters.

56. **`test_normalize_parameters_rejects_unknown_material_type`**
    - Rejects unsupported artifact/material types.

57. **`test_empty_parameters_are_canonical`**
    - Verifies empty parameter sets have a canonical representation.

58. **`test_first_generation_calls_provider_and_second_identical_request_reuses`**
    - First request calls the provider.
    - Identical later request reuses the ready artifact instead of paying for another generation.

59. **`test_inflight_identical_request_attaches_without_provider_duplicate`**
    - Concurrent identical requests attach to the in-flight generation rather than duplicating provider work.

60. **`test_reused_ready_artifact_does_not_check_entitlement`**
    - Verifies a ready reusable artifact follows the intended reuse path without incorrectly re-consuming the generation entitlement.

61. **`test_flashcard_variant_pool_rotates_four_versions_before_reuse`**
    - Verifies four generation variants rotate before reuse.

62. **`test_all_document_materials_use_the_shared_four_variant_pool`**
    - Verifies summary, quiz, flashcards, podcast, and mind map use the shared variant-pool mechanism.

63. **`test_generation_request_ceilings_are_enforced`**
    - Parametrized over four material types:
      - summary: maximum 10 pages
      - podcast: maximum 50 minutes
      - flashcards: maximum 50 cards
      - mind map: maximum 50 nodes
    - This is the reason the 71 functions become 74 collected pytest cases.

64. **`test_generation_store_exposes_inflight_family_lookup`**
    - Verifies the generation store exposes the in-flight family lookup required for request coalescing.

### J. `tests/test_realtime_e2ee_runtime.py` — 8 test functions

65. **`test_socket_membership_and_same_conversation_delivery`**
    - Creates an E2EE direct conversation between student A and B.
    - Verifies both members can join.
    - Verifies the admin outsider is denied.
    - Sends an encrypted payload through the real HTTP message route.
    - Verifies the receiver gets the persisted encrypted message over realtime.

66. **`test_direct_e2ee_plaintext_is_rejected_before_persistence`**
    - Sends plaintext to a direct E2EE conversation.
    - Verifies HTTP 409.
    - Verifies plaintext was not persisted.

67. **`test_chat_retry_is_idempotent_and_does_not_duplicate_message`**
    - Sends the same client message twice.
    - Verifies the retry returns the same message identity rather than creating a duplicate row.

68. **`test_offline_receiver_recovers_from_database_history`**
    - Sends an encrypted message while the receiver is not connected to realtime.
    - Verifies the receiver can recover it from PostgreSQL chat history.

69. **`test_socket_session_version_and_suspension_are_enforced`**
    - Verifies a valid session can connect.
    - Rotates the user's session version and verifies the stale socket is rejected.
    - Suspends the user and verifies a new socket is rejected.

70. **`test_frontend_realtime_contract_matches_backend`**
    - Verifies frontend and backend agree on realtime event names and important Socket.IO behavior.
    - Checks credentials, reconnection, disconnect behavior, and offline client message IDs.

71. **`test_realtime_deployment_contains_dedicated_chat_worker`**
    - Verifies the production-style Compose stack contains the dedicated `chat-worker`.
    - Verifies Redis configuration and worker consumption/channel wiring.

72. **`test_redis_stream_queue_is_not_treated_as_postgres_source_of_truth`**
    - Verifies the code explicitly treats PostgreSQL as durable source of truth.
    - Verifies Redis Stream enqueue/ack/recovery primitives exist.

## 5. Coverage map

The 74 collected cases cover these major boundaries:

| Area | What is proven |
|---|---|
| Flask route registration | Critical routes exist and duplicate registrations are detected |
| Route dispatch | Registered routes are exercised through the real Flask app |
| Authentication | Anonymous vs authenticated access boundaries |
| Authorization | Student/admin separation and organisation tenant isolation |
| CSRF | State-changing security boundary |
| Session security | Logout, session-version rotation, suspension |
| Organisations | Creation, ownership, verification, targeting, submission |
| Opportunities | Draft → pending review → approved → published lifecycle |
| Targeting | University/program/year/semester targeting and profile changes |
| Rate limiting | Real limiter still permits legitimate organisation activity |
| Concurrency | Duplicate save and concurrent organisation-read behavior |
| B2B economics | Prepaid balance and campaign pricing protection |
| AI frontend contract | Frontend route/payload names match backend |
| AI artifact identity | Fingerprint determinism, scope, owner, parameters, prompt/schema |
| AI generation ownership | Only the intended producer can invoke provider work |
| AI economics | Unit weights, rounding, plan defaults, feature flags, Paystack sync |
| AI reuse | Cache reuse, in-flight coalescing, four-variant rotation |
| AI request limits | Exact per-request ceilings |
| Realtime membership | Only conversation members can join |
| Realtime delivery | Same-conversation encrypted messages reach members |
| E2EE | Plaintext is rejected before persistence |
| Chat idempotency | Client retry does not duplicate messages |
| Offline recovery | PostgreSQL history restores messages after missed realtime |
| Realtime auth | Session version and suspension are enforced on sockets |
| Frontend realtime contract | Frontend event contract matches backend |
| Redis architecture | Dedicated worker and Redis Stream path are structurally present |
| Source of truth | PostgreSQL remains durable chat truth; Redis is delivery infrastructure |

## 6. What this suite does NOT prove by itself

The 74/74 result is strong local integration evidence, but it is not the entire production deployment proof.

It does **not by itself** prove:

- a real external Redis multi-process Socket.IO deployment under live network conditions;
- the separate focused `scripts/test_realtime_runtime.py` production-style runtime smoke test;
- the separate `scripts/test_calling_runtime.py` calling runtime smoke test;
- real OpenAI, Paystack, SES, R2, or other external provider availability;
- real browser rendering/visual QA on every device;
- real internet/network failure behavior;
- production VPS performance under real traffic.

Those are separate audit gates. The project should not call the realtime/calling production-style gate GREEN until those explicit runtime checks pass.

## 7. Why the suite uses controlled users instead of real accounts

The suite needs deterministic identities so it can safely test:

- tenant boundaries;
- admin boundaries;
- session invalidation;
- suspended accounts;
- conversation membership;
- E2EE sender/receiver behavior;
- entitlement ownership;
- targeting differences.

All data lives in the disposable `prepza_qa` PostgreSQL database. The fixture resets that database and recreates the controlled world.

This is what makes a 74-case integration run repeatable rather than dependent on whichever real accounts happen to exist on a developer laptop.

## 8. Interview explanation

A strong way to explain the suite is:

> "I built a disposable PostgreSQL-backed integration test environment around the real Prepza Flask application. The full runner executes 10 test modules containing 71 test functions and 74 collected pytest cases. The test world creates seven controlled users—six students and one admin—with two organisation tenants. The suite exercises route registration and dispatch, authentication and authorization, CSRF and session invalidation, organisation/opportunity workflows, targeting, rate limits, B2B metering, AI economics and artifact reuse, and realtime/E2EE behavior. It deliberately uses real PostgreSQL and Alembic migrations, while isolating Redis-dependent test behavior so the test environment remains deterministic. The 74/74 result gives us evidence across the application boundaries rather than only proving individual functions exist."

## 9. Current relationship to production-style runtime tests

The full QA suite and the focused runtime scripts answer different questions.

**Full QA suite:** "Does the application behave correctly against the disposable PostgreSQL-backed application environment across all these contracts?"

**Focused realtime/calling runtime tests:** "Does the production-style Socket.IO/Redis/calling deployment path actually work when the real services are running?"

Both are necessary. Passing one does not make the other unnecessary.

---

**Last verified full-suite result:** 74 passed, 0 failed, 3375 warnings.


## 7. 2026-10-05 — Authoritative test inventory and release-gate status

This section records the current inventory after the self-contained focused realtime/calling fixture work. It deliberately distinguishes **implemented**, **executed**, **passed**, and **production-proven**.

### A. Tests already executed

| Gate / command | Coverage | Latest known evidence | Status |
|---|---|---|---|
| `python tools/run_local_qa.py` | Disposable PostgreSQL + Alembic + the 10-file real-world suite below | **74 passed, 0 failed, 3375 warnings** on the documented full run | GREEN |
| `pytest scripts/test_calling_runtime.py -q` | Authenticated Socket.IO 1:1 call signaling | **4 passed in 3.31s** after the fixture/auth reconciliation | GREEN |
| `pytest scripts/test_realtime_runtime.py -q` | Focused authenticated Socket.IO chat presence, membership, delivery, multi-tab presence and message dispatch | Executed in the focused-runtime verification sequence; the exact latest numeric result is not preserved in the current repository notes | **Do not infer a result** |
| Redis-backed Compose inspection | Production-style Redis configuration + dedicated chat worker | Compose/runtime path is documented separately; local full QA intentionally uses `REDIS_URL=memory://` | PARTIAL / separate gate |

**Important:** the missing numeric result above is intentional. We do not turn “the command was run” into “the command passed” without preserved evidence.

### B. Full local QA files — reuse, do not duplicate

The authoritative full suite currently reuses these 10 files:

1. `tests/test_local_qa_real_world.py`
2. `tests/test_route_security_matrix.py`
3. `tests/test_authenticated_route_matrix.py`
4. `tests/test_local_qa_authz.py`
5. `tests/test_frontend_ai_generation_contract.py`
6. `tests/test_ai_artifact_fingerprint.py`
7. `tests/test_ai_generation_store.py`
8. `tests/test_ai_economics.py`
9. `tests/test_ai_reusable_generation.py`
10. `tests/test_realtime_e2ee_runtime.py`

Together they are currently **71 test functions / 74 collected cases**.

Focused runtime scripts remain outside that 74-case suite because they exercise a different purpose:

- `scripts/test_realtime_runtime.py` = authenticated Socket.IO runtime smoke/regression behavior.
- `scripts/test_calling_runtime.py` = authenticated WebRTC signaling runtime behavior.
- `scripts/runtime_test_fixtures.py` = disposable real database users for those focused runtime tests.

### C. Master release-gate model

The future single command should orchestrate existing gates rather than duplicate their assertions:
**Gate 1 — Environment/database**
- Compose services healthy.
- Database reachable.
- Alembic/migration state valid.

**Gate 2 — Authentication/session**
- Anonymous rejection.
- Login/session creation.
- Logout/session-version invalidation.
- Suspended-session rejection.

**Gate 3 — Authorization/ownership**
- Student/admin separation.
- Organisation tenant isolation.
- Conversation membership.
- CSRF/state-changing boundaries.

**Gate 4 — Economics**
- Free/Plus/Pro canonical entitlements.
- Exact quota consumption and remaining quota.
- Per-request ceilings.
- Expiry/future-start boundaries.
- Paystack price/currency/idempotency contract.
- B2B prepaid metering.

**Gate 5 — AI runtime**
- Frontend/backend generation contract.
- Artifact identity.
- Ownership.
- Ready-artifact reuse.
- In-flight coalescing.
- Variant rotation.
- Provider policy.

**Gate 6 — Realtime/E2EE**
- Full PostgreSQL-backed E2EE integration suite.
- Focused authenticated Socket.IO runtime.
- Redis-backed production-style path.
- Dedicated chat-worker consumption/recovery.

**Gate 7 — Calling**
- Authenticated invite.
- Exact two-member membership.
- Offer/answer/ICE authorization.
- Target-only signaling.
- End/cleanup.

**Gate 8 — Storage/data integrity**
- Persistence after successful operations.
- No plaintext E2EE persistence.
- Attachment/document storage contracts.
- R2/Supabase provider behavior where locally testable.

**Gate 9 — PWA/offline**
- Offline architecture checks.
- IndexedDB/local queue behavior.
- Recovery/synchronization boundaries.

**Gate 10 — Failure/concurrency**
- Duplicate-save race safety.
- Concurrent reads.
- Retry/idempotency.
- Load/stress checks where the test can run without inventing credentials.

The master runner must report each gate separately and fail the overall run if a required gate fails. Individual tests remain the diagnostic tools.

### D. Evidence rules

A future green release report must record four separate facts:

1. **Implemented** — the code/test exists.
2. **Executed** — the command actually ran.
3. **Passed** — the command returned a passing result.
4. **Proven in production-like infrastructure** — where a test depends on Redis, external providers, deployment networking, or real browser/device behavior, local unit/integration success is not enough.

This prevents a common QA mistake: treating the existence of a test or a green static contract as proof that a real student operation works.

### E. Current blockers / next verification

The 74/74 local integration suite is GREEN and the focused calling runtime is GREEN.

The remaining release-gate evidence is intentionally separate:

- preserve/verify the exact latest focused realtime runtime result;
- verify the actual Redis-backed Socket.IO/chat-worker path;
- complete storage/provider-specific verification;
- add the master orchestrator only after the existing gate inventory remains stable.

No production deployment, VPS purchase, GPU purchase, or paid infrastructure change is part of this local gate.


## 2026-10-05 — Focused authenticated realtime runtime verified

The previously unpreserved focused realtime result has now been executed from a freshly rebuilt Docker application environment and recorded exactly.

### Command

```text
docker compose -f docker-compose.vps.yml exec -e REDIS_URL=memory:// app python -m pytest scripts/test_realtime_runtime.py -q
```

### Result

```text
.........                                      [100%]
9 passed in 2.98s
```

### What this proves

The focused authenticated Socket.IO runtime smoke/regression suite is GREEN for its 9 cases, covering:

- unauthenticated socket rejection;
- conversation membership enforcement;
- legitimate member join/presence;
- repeated-join protection;
- disconnect presence;
- multi-tab presence;
- explicit leave/presence behavior;
- authenticated typing/read/message dispatch;
- non-member leave authorization.

The test uses disposable database-backed authenticated users and their real session versions. This preserves the real authentication boundary rather than bypassing it.

### Important boundary

This result uses `REDIS_URL=memory://` because the focused Flask-SocketIO test client is intentionally run in-process. Therefore this is evidence that the authenticated realtime application behavior works; it is **not** evidence that the production multi-process Redis + dedicated chat-worker path works.

### Current focused runtime evidence

- Focused realtime Socket.IO runtime: **9 passed in 2.98s — GREEN**
- Focused calling runtime: **4 passed in 3.31s — GREEN**
- Full local integration suite: **74 passed, 0 failed, 3375 warnings — GREEN**
- Redis-backed production-style runtime: **NEXT GATE / NOT YET PROVEN**

### Next local verification

The next test must target the **actual Redis-backed Compose path**, including the running Redis service and dedicated chat worker. We should not add duplicate application assertions. The purpose is to establish whether the cross-process delivery/worker path works with the real `redis://redis:6379/0` configuration.

No paid infrastructure or production deployment is involved.


## 2026-10-05 — Redis-backed chat-worker runtime gate prepared

The next realtime gate is deliberately **not** another in-process Socket.IO test.

Added:

- scripts/test_redis_chat_worker_runtime.py

This focused runtime check requires a real redis:// or rediss:// connection and starts the actual chat_event_worker.py process with isolated Redis Stream/group names.

It verifies:

1. the worker creates its real Redis consumer group;
2. a chat event is placed on the Redis Stream;
3. the real worker consumes the event;
4. the worker acknowledges the Stream entry;
5. the worker publishes the resulting chat:message event to the prepza-realtime Socket.IO Redis channel for the correct conversation room.

This is stronger than the existing memory:// Socket.IO tests because it exercises the actual Redis Stream + worker process + Socket.IO Redis message-queue boundary.

**Important limitation:** this still does not prove that a browser/client connected to a separate realtime process receives the event. That final client-facing multi-process hop remains a separate deployment-level check.

**Execution status:** PREPARED / NOT YET EXECUTED.

Exact intended command after refreshing local main:

    docker compose -f docker-compose.vps.yml build app
    docker compose -f docker-compose.vps.yml up -d --force-recreate app realtime chat-worker
    docker compose -f docker-compose.vps.yml exec app python -m pip install -r requirements-test.txt
    docker compose -f docker-compose.vps.yml exec app python scripts/test_redis_chat_worker_runtime.py

Do not classify the Redis-backed realtime gate as green until this command actually passes.


## 2026-10-05 — Redis-backed chat worker gate passed

### Exact local command

    docker compose -f docker-compose.vps.yml exec app python scripts/test_redis_chat_worker_runtime.py

### Exact result

    PASS: real Redis chat worker consumed and acknowledged the event
    PASS: worker published chat:message onto prepza-realtime for the conversation room
    PASS: Redis stream entry 1791203715146-0 was processed

### What this proves

The real Docker Redis path is now **GREEN** for the dedicated chat-worker boundary:

- the worker reached the actual Redis service;
- the worker consumed the controlled Redis Stream event;
- the worker acknowledged the Stream entry;
- the worker published the expected `chat:message` event through the `prepza-realtime` Socket.IO Redis channel;
- the event was targeted to the expected conversation room.

This is separate evidence from the earlier in-process `REDIS_URL=memory://` Socket.IO tests.

### What it does not yet prove

It does not yet prove that a real connected Socket.IO client/browser receives that Redis-published event through the **separate realtime container**.

The remaining local hop is:

    Redis Socket.IO publication
        ↓
    separate realtime process
        ↓
    connected Socket.IO client

### Next local gate

Run:

    docker compose -f docker-compose.vps.yml exec app python scripts/test_redis_realtime_client_runtime.py

This new test is intentionally different from the existing 9-case Socket.IO suite: it uses the real Docker Redis service, starts the real chat worker, connects a real Socket.IO client to the separate `realtime` container, creates real database-backed conversation membership, injects one isolated Redis Stream event, and verifies the connected client receives the resulting `chat:message`.

No paid infrastructure or production deployment is involved.


### 2026-10-05 — Cross-process client test harness correction

The first execution of the new client-facing Redis/realtime gate was blocked before the test logic ran:

    ModuleNotFoundError: No module named 'app'

Cause: when Compose executes `python scripts/test_redis_realtime_client_runtime.py`, Python starts with `/app/scripts` on the import path, while the Flask application module is at the repository root `/app/app.py`.

This was a test-harness import-path defect, not a realtime/runtime failure. The script was corrected to add the repository root to `sys.path` before importing the application modules.

The distributed realtime assertions have **not** been scored yet. Re-run the same gate after refreshing `main`.


## 2026-10-05 — Cross-process realtime client delivery gate passed

### Exact command

    docker compose -f docker-compose.vps.yml exec app python scripts/test_redis_realtime_client_runtime.py

### Exact result

    PASS: real Socket.IO client connected to the separate realtime process
    PASS: authenticated client joined the real database-backed conversation
    PASS: Redis Stream -> chat-worker -> Redis Socket.IO queue -> realtime process -> client delivered chat:message
    PASS: Redis stream entry 1791205395549-0 was acknowledged
### What this proves

The final Redis-backed cross-process realtime delivery gate is now **GREEN**.

This test exercised the actual distributed path:

    real Redis Stream
        ↓
    real chat_event_worker.py
        ↓
    Redis Socket.IO message queue
        ↓
    separate realtime container
        ↓
    real authenticated Socket.IO client

The client joined a real PostgreSQL-backed conversation, the controlled event traversed the worker and Redis Socket.IO queue, and the connected client received the expected `chat:message`. The Redis Stream entry was also acknowledged.

This closes the previously unproven browser-facing distributed realtime hop for the tested single-message path.

### Important boundary

This is strong local Docker evidence, not proof of a public production deployment under internet load. It does prove the complete local multi-process Redis/realtime/client chain works in the production-style Compose architecture.

It does not by itself prove browser behavior in every frontend state, high-load behavior, external network conditions, or production-provider configuration.

### Current realtime evidence

- Full local integration suite: **74 passed, 0 failed, 3375 warnings — GREEN**
- Focused authenticated realtime runtime: **9 passed in 2.98s — GREEN**
- Focused calling runtime: **4 passed in 3.31s — GREEN**
- Redis-backed chat-worker gate: **GREEN**
- Redis-backed cross-process realtime client delivery: **GREEN**

### Important debugging lesson

The first execution failed before reaching any realtime assertion because the container contained an older copy of the test script and raised:

    ModuleNotFoundError: No module named 'app'

The repository and local checkout already contained the fix, so we rebuilt the app image with:

    docker compose -f docker-compose.vps.yml build --no-cache app

After force-recreating the app, realtime, and chat-worker containers, the container contained the corrected import path and the actual distributed test passed.

This is a useful source-of-truth lesson: when Git contains the expected code but a container executes different code, inspect the code inside the running image before diagnosing application behavior.


## 2026-10-05 — Real browser-to-browser WebRTC calling gate prepared

### Why this gate exists

The focused calling runtime is already green at the authenticated Socket.IO signaling layer (**4 passed in 3.31s**), but that does not prove actual microphone/media connectivity between two browsers.

The next missing calling boundary is:

    Browser A
        ↓ getUserMedia
    RTCPeerConnection
        ↓ offer/answer/ICE through real Socket.IO
    Browser B
        ↓ RTCPeerConnection
    remote MediaStream

### New test

Added:

    scripts/test_browser_webrtc_runtime.py

The test is intentionally a host-side browser test rather than a pytest-only Socket.IO test. It:

1. Creates two disposable real database users and one real PostgreSQL-backed 1:1 conversation through the running Docker app container.
2. Launches two independent Chromium browser contexts with fake microphone/camera devices.
3. Logs both browsers in through the real `POST /login` endpoint.
4. Starts the call through the same `prepza-start-call` event used by the real Prepza calling UI.
5. Accepts the incoming call in the second browser.
6. Waits for both browsers to report the real calling UI's **Connected** state.
7. Verifies both browser pages have a live remote audio `MediaStreamTrack`.
8. Cleans up the disposable users/conversation.

### Required host setup

From the repository root:

    python -m pip install playwright
    python -m playwright install chromium

The Docker production-style stack must already be running and the app must be reachable at:

    http://127.0.0.1:5000

Then run:

    python scripts/test_browser_webrtc_runtime.py

### Status

**PREPARED / NOT YET EXECUTED.**

This gate is deliberately different from the existing 4-case calling runtime. The earlier test proves signaling/authentication; this one is intended to prove actual browser WebRTC media.

No paid infrastructure, VPS migration, GPU purchase, or public deployment is involved.

### Important limitation

A green local browser gate proves the implemented WebRTC path works under controlled localhost/fake-media conditions. It does **not** prove real student devices behind arbitrary NAT/firewalls can always connect. That later belongs to deployed-environment/network QA, including the configured ICE/STUN/TURN strategy if required.


## 2026-10-05 — Browser WebRTC gate: first execution blocked by harness defects

The first execution of `scripts/test_browser_webrtc_runtime.py` reached real browser authentication successfully:

    PASS: disposable browser-call users and conversation created
    PASS: two independent real browser contexts authenticated

It then stopped before WebRTC signaling because the test assumed `/me` returned a top-level `id`, but the actual response shape did not match that assumption:

    KeyError: 'id'

The cleanup path also exposed a fixture-cleanup defect: browser authentication created dependent `user_key` rows, so deleting the disposable users directly failed with a PostgreSQL foreign-key violation.

This is a **test-harness failure, not a calling failure**. The test did not reach offer/answer, ICE, RTCPeerConnection, or media assertions.

### Correction made on main

Commit:

    f3eb880c718f1f564bca83829bb62f3fddbd2786

The browser gate now:

- accepts the actual `/me` payload shape (while failing clearly if it is unexpected);
- deletes dependent `user_key` rows before deleting disposable users during cleanup.

### Status

**NOT YET PROVEN.**

The real browser WebRTC gate must be executed again after the corrected script is present locally and the Docker app stack is refreshed as needed.


## 2026-10-05 — Browser WebRTC gate: corrected harness for session and cleanup

The next browser run exposed two more **test-harness** issues before WebRTC media could be evaluated:

1. The local browser test used the numeric `http://127.0.0.1:5000` origin while the Flask application sets its session cookie as `Secure`. The test could therefore authenticate at the HTTP response level without reliably sending the session cookie on the follow-up `/me` request.
2. The cleanup SQL was inside a Python f-string, so the dictionary expression `{"user_ids": user_ids}` was interpreted as an f-string formatting expression.

### Corrections made on main

The browser gate now:

- defaults to `http://localhost:5000`, which is the appropriate local origin for browser testing with Secure cookies;
- verifies the authenticated session by calling `/me` immediately after login;
- returns the real authenticated user ID from that verification instead of making a second unauthenticated assumption;
- escapes the cleanup dictionary braces correctly;
- adds Playwright to `requirements-test.txt` so the Python browser-test dependency is part of the repository's test environment.

Chromium itself remains a separately installed browser binary via:

    python -m playwright install chromium

We are intentionally keeping Chromium out of the production/app Docker image because this is a host-side browser integration test.

### Status

**CORRECTED / NOT YET EXECUTED.**

The browser WebRTC gate still must pass before calling the calling gate green.

The earlier failures remain classified as harness defects; no application WebRTC failure has yet been demonstrated.


### 2026-10-05 — Browser WebRTC gate: instrumented incoming-call UI timeout

The latest browser gate reached real browser authentication but timed out waiting for the callee's `Accept call` button. Rather than changing the selector blindly, the test was instrumented to print the callee's visible button labels and visible body text when that timeout occurs. This will distinguish a stale/incorrect test selector from a real failure to render or deliver the incoming-call UI.

Change committed directly on `main`: `f9c15426b4ed352503e453a837d08880dffbeb23` (`test: diagnose browser call accept UI`).

The WebRTC browser-to-browser gate remains **NOT YET PROVEN**. No storage/data-integrity gate should start until this browser call path is resolved and rerun.


### 2026-10-05 — Browser WebRTC gate: real onboarding blocker identified

The instrumented browser run reached real authentication but the callee page rendered `1/4 Finish setting up` and no buttons. The visible page also reported that the university was not found. This proves the timeout was not an incorrect `Accept call` selector: the disposable test account was being held in the real first-run onboarding flow, so the chat/call shell was never mounted and no incoming-call UI could exist.

The browser fixture has now been corrected to use an existing active university and active program from the real database when creating its disposable caller/callee accounts. It still uses the normal login and onboarding state; it does not bypass onboarding or inject a fake call UI.

Change committed directly on `main`: `623e7ae4d06d8b9cacd3781f49f335f2b4977b05` (`test: satisfy onboarding in browser call fixture`).

Result classification: **TEST-HARNESS FIX / REAL APP BEHAVIOR EXPLAINED**. The WebRTC browser-to-browser gate remains **NOT YET PROVEN** until the corrected fixture reaches the call UI and completes the actual media test.

Important lesson: a successful `/login` response is not sufficient evidence that a real Prepza user has reached the authenticated application shell. The browser gate must satisfy the same onboarding prerequisites a real user must satisfy.


### 2026-10-05 — Browser WebRTC gate: fixture error-formatting defect

The next execution of the browser WebRTC gate stopped before any browser interaction because the fixture-building Python code raised:

    NameError: name 'university' is not defined

The defect was in the **test harness**, not the application. The browser fixture is itself constructed from an outer Python f-string, and the inner error message used `{university.id}`. Python therefore tried to evaluate that expression while constructing the fixture source string, before the generated fixture code had assigned `university`.

The fixture logic itself is correct: it queries an active university and then an active program for that university. Only the error-message construction was wrong.

Correction committed directly on `main`:

    2a256a54628fa01a3059fc3ab385affd2e80c95c

The error now builds the message with string concatenation, avoiding accidental evaluation by the outer f-string.

### Status

**NOT YET PROVEN.** The browser-to-browser WebRTC media gate has still not reached the actual call UI/media assertions. The next run should execute the corrected fixture and determine whether the real call flow proceeds past onboarding.


### 2026-10-05 — Browser WebRTC gate: local reference-data prerequisite missing

The corrected browser WebRTC fixture now executed its intended database lookup, but the run stopped before creating users or launching Chromium with:

    RuntimeError: Container fixture command failed:
    RuntimeError: No active university exists for browser WebRTC fixture

This is not a browser selector failure, authentication failure, calling failure, or WebRTC failure. The disposable fixture correctly requires a real active university and active program so the accounts satisfy the same onboarding prerequisites as normal users.

Repository inspection found the supported reference-data seed script already present on main: `seed_universities_and_programs.py`. It is documented as idempotent and seeds the university/program catalog from the repository's institution data. The local database currently has no active university row, so the browser fixture cannot honestly proceed without the reference data being present.

No fake university/program data should be invented inside the browser test. The next step is to run the repository's existing seed mechanism against the local QA database, then rerun the unchanged browser WebRTC gate.

### Status

**NOT YET PROVEN.** No browser/WebRTC assertion has run in this attempt. The blocker is local database reference-data initialization.


### 2026-10-05 — Browser WebRTC gate: reference data fixed; call UI mount + cleanup defects exposed

The local reference-data prerequisite is now satisfied using the repository's existing seed mechanism:

    [DRY RUN] Would create 103 new universities.
    [DRY RUN] Would create 15038 new programs.
    Created 103 new universities.
    Created 15038 new programs.
    Active universities: 103
    Active programs: 15038

The browser gate then reached real browser authentication successfully, but timed out waiting for the callee's **Accept call** button. Diagnostics showed the callee was on the authenticated Home shell. Repository inspection confirmed the reason: `CallExperience` is mounted by `WhatsAppChatExperience`, so the test was dispatching the start-call event without opening the real conversation route where the call UI exists.

The same run also exposed a test-fixture cleanup defect: first-run authenticated use creates a `study_streak` row, so deleting the disposable users directly violates `study_streak_user_id_fkey`.
The browser gate was corrected on main to:
- open `/chats/{conversation_id}` in both real browser contexts before starting the call;
- remove dependent `study_streak` rows during disposable-user cleanup.

Commit: `32d58d6612731e8129546d49c302887b20c7b71a`.

**Status: NOT YET PROVEN.** The application has not yet passed the real browser-to-browser WebRTC media assertion. The latest timeout was a test-navigation prerequisite, not evidence that WebRTC media is broken.


### 2026-10-05 — Chat/calling UX audit and global incoming-call redesign

A repository-grounded audit of the active React chat/calling implementation found several important product and integration issues before the browser WebRTC gate could honestly be called green:

- CallExperience was mounted inside WhatsAppChatExperience, so incoming-call UI depended on the chat route being mounted. This does not match the intended messaging-app interaction model: an authenticated student should be able to receive an incoming call while on Home or another Prepza screen.
- A second CallExperience instance also existed in the legacy ChatDetailScreen path, creating duplicate call-listener risk if that path is ever rendered.
- CallExperience used Unicode symbols (×, ✓, ⌁, ◉) as functional call controls. Production calling controls must use proper custom SVG controls with accessible names/tooltips. User-content emoji reactions remain valid as content; application controls do not use emoji characters.
- Outgoing calls had no finite no-answer timeout. If the callee was offline, the server had no connected target to deliver the invite to, while the frontend could remain in Calling… indefinitely.
- The realtime invite path did not return whether the target user was actually connected. It now reports delivery count and rejects an invite immediately as User unavailable when there is no connected target.
- Call signaling acknowledgements were previously fire-and-forget. The client now awaits Socket.IO acknowledgements for call events, with a bounded realtime timeout.
- The browser WebRTC gate was updated to test the intended UX contract: the caller opens the real chat and uses the real Start voice call button, while the callee remains on Home. The incoming-call UI must therefore be globally available.

Implementation committed directly on main:
- frontend/src/crypto/callRealtime.ts — bounded/acknowledged call signalling.
- frontend/src/crypto/CallExperience.tsx — global call identity resolution, unavailable/no-answer handling, 30-second incoming/outgoing timeout, and custom SVG call controls.
- frontend/src/crypto/WhatsAppChatExperience.tsx — removed duplicate route-local CallExperience.
- frontend/src/App.tsx — mounted one CallExperience at the authenticated app shell level.
- realtime_server.py — call invite now reports delivery and returns User unavailable when no target socket exists.
- scripts/test_browser_webrtc_runtime.py — browser gate now verifies a real caller UI action and global callee incoming UI.

Status: IMPLEMENTED, NOT YET LOCALLY EXECUTED. The next step is to refresh local main, run the frontend build, then run the browser WebRTC gate. If the gate reaches Accept/Connected, continue with offline, decline, timeout, and media assertions. Group-call/add-participant work remains a separate design/architecture phase because the current realtime backend explicitly limits calls to exactly two conversation participants.


### 2026-10-05 — First local build after calling UX redesign: FAILED at prebuild

The local Docker image build reached the frontend prebuild successfully but failed before Vite compilation. The failing prebuild step was `python3 ../tools/apply_call_history.py`, which reported `CALL_HISTORY_FAILED: incoming handler missing` because the call-history source transformer expected the old one-line incoming-call handler after the CallExperience redesign changed that handler to include global-call timeout/delivery logic.

No browser/WebRTC test was run from this build because the frontend image was not successfully built. Docker Compose subsequently started the existing app/realtime/chat-worker containers, but those containers are not evidence that the new frontend build succeeded.

The build transformer has now been reconciled to the new CallExperience structure and made idempotent. The call listener dependency was also corrected to subscribe when the resolved user identity changes. Local verification is still pending.

## 2026-10-05 — Docker production-style app image rebuild: GREEN

### Command executed

    git fetch origin
    git reset --hard origin/main
    docker compose -f docker-compose.vps.yml build app

### Result

- Local checkout synchronized to origin/main at c09c7eb (fix global call realtime listener dependency).
- Docker app image build completed successfully.
- Build completed in approximately 78.4 seconds.
- All 22/22 Docker build steps completed.
- Frontend stage completed successfully with pnpm install --frozen-lockfile && pnpm run build.
- Runtime image completed successfully and was exported as prepza-app:latest.
- Previous CALL_HISTORY_FAILED: accept handler missing build blocker is resolved.

### Interpretation

**RESULT: GREEN — application image builds successfully from current main.**

This proves the current source tree can pass the Dockerized frontend prebuild/transform chain and produce the application image. It does not yet prove runtime behavior, browser WebRTC media, or production provider integrations.

### Release-gate status

- Docker app image build: **GREEN**
- Browser-to-browser WebRTC media: **NOT YET PROVEN**
- Storage/data-integrity gate: **BLOCKED until browser calling gate is resolved**

### Lesson recorded

A successful Docker build is an important boundary check, but it is not a substitute for runtime testing. The image is now proven buildable; the next step is to recreate the runtime services from this image and rerun the relevant QA/browser gates.


## 2026-10-05 — Full local QA after production-style service recreation: GREEN

### Command executed

    docker compose -f docker-compose.vps.yml exec app python tools/run_local_qa.py

### Result

- QA database: `prepza_qa` (existing disposable database retained for inspection)
- Alembic migrations: **OK**
- Full real-world and route semantic QA suite: **74 passed, 0 failed**
- Runtime: **54.89 seconds**
- Warnings: **3375**

### Interpretation

This is a **GREEN full local integration/regression result** after recreating the production-style application, realtime, and chat-worker services from the successfully rebuilt image.

The suite exercised authentication/session boundaries, authorization and organisation isolation, route dispatch, economics/entitlements, Paystack contract behavior, AI generation identity/reuse/ceilings, E2EE chat, realtime membership/delivery, retry idempotency, offline recovery, and Redis/chat-worker deployment contracts.

The warnings are not test failures. They are primarily existing technical-debt warnings around deprecated `datetime.utcnow()` usage and one legacy SQLAlchemy `Query.get()` call.

### Release-gate interpretation

- Full local QA: **GREEN (74/74)**
- Docker image build: **GREEN**
- PostgreSQL/Redis/app/realtime/chat-worker startup: **GREEN**
- Real browser-to-browser WebRTC media: **NOT YET PROVEN**
- External provider/storage recovery: **NOT YET PROVEN**

The full QA result does not replace the separate browser WebRTC gate or the later storage/data-integrity and real-provider gates.


## Browser WebRTC gate — first host run (2026-10-05)
- Command: `python scripts/test_browser_webrtc_runtime.py`
- Result: **RED — test harness timing failure before call initiation**.
- Proven before failure: disposable users/conversation created; two independent browser contexts authenticated; caller opened the real conversation while callee remained on Home.
- Failure: Playwright timed out waiting 30s for the real `Start voice call` button.
- Interpretation: this does not yet prove a WebRTC/backend failure. The test was using a fixed 1.2s post-navigation wait before looking for a control whose rendering depends on the asynchronously loaded conversation detail/participant state.
- Fix on `main`: browser gate now explicitly waits up to 15s for the real call button and dumps caller buttons/body text if it is still absent, so the next run distinguishes a render race from a genuine missing-control/data problem.
- Commit: `aa67d88d326e4518606197d4569ffd0cf8ec427b`.
- Next required run: `python scripts/test_browser_webrtc_runtime.py` after syncing to `origin/main`.


## Browser WebRTC gate — chat-list visibility failure and fix (2026-10-06)
- Re-ran `python scripts/test_browser_webrtc_runtime.py` from `86dbcc8`.
- Disposable users/conversation were created and both real browser contexts authenticated.
- Diagnostic `GET /chats` returned HTTP 200 with conversation id 12, confirming the backend/session boundary was working.
- The returned direct-chat row had `name: null`; the browser DOM remained on the Home shell after the Chats click and the expected peer row never appeared within 10 seconds.
- Root cause identified in `frontend/src/crypto/WhatsAppChatExperience.tsx`: the component initialized `visible=false`, while its own `/chats` request is marked internal and therefore intentionally bypasses the fetch observer that previously promoted the component to visible. Because the component is mounted only for the Chats screen, that observer must not be the primary visibility gate.
- Fix committed directly to `main` as `a9300823f592f205ce91f773c7ed82273108ba9f`: initialize the mounted Chats experience as visible, resolve null direct-chat names from conversation participants, and make name filtering/rendering null-safe.
- **Status: fix committed; browser WebRTC gate is pending re-run.**


### 2026-10-06 — Browser WebRTC gate build regression and source fix
- Re-ran the browser WebRTC gate after the chat-list visibility fix.
- Docker frontend build failed during TypeScript compilation in `WhatsAppChatExperience.tsx`: `visible`/`setVisible` were reported undefined and `ChatSummary.last_message` was missing from the type.
- Root cause: the explanatory comment inserted above the visibility state contained literal `\\n` characters, so the `const [visible, setVisible] = useState(true)` declaration was effectively commented out. The `ChatSummary` type also lacked the optional `last_message` field already consumed by the chat-list hydration/rendering path.
- Fix committed directly on `main`: `18aff73` (`fix: restore chat visibility state and summary preview type`).
- Browser test did not reach WebRTC; the rebuilt app must pass TypeScript/build first, then the browser gate must be re-run.


### 2026-10-06 — Browser WebRTC gate source correction and successful Docker rebuild

- After commit `bd3e5fb`, inspection of the checked-out source showed that `WhatsAppChatExperience.tsx` still contained a literal `\n` inside the visibility comment.
- This caused `const [visible, setVisible] = useState(true)` to remain part of the comment, producing the TypeScript `visible`/`setVisible` undefined errors.
- The malformed literal was corrected directly in `frontend/src/crypto/WhatsAppChatExperience.tsx`.
- `git diff --check`: **GREEN — no whitespace errors**.
- Docker rebuild command:

      docker compose -f docker-compose.vps.yml build app

- Result: **GREEN — 22/22 Docker build steps completed successfully**.
- Frontend `pnpm install --frozen-lockfile && pnpm run build`: **GREEN**.
- Runtime image `prepza-app:latest`: **SUCCESSFULLY BUILT**.

### Interpretation

The source/build boundary is now green. The application image can again be produced from the corrected working tree, so the previous TypeScript blocker is resolved.

The browser WebRTC gate remains **NOT YET PROVEN**. The newly built image must be recreated into the running application container before browser testing. The previously observed `/me` HTTP 429 is a separate rate-limit issue and must be investigated independently rather than conflated with the WebRTC path.

### Current release-gate status

- Docker app image build: **GREEN**
- TypeScript/Vite frontend build: **GREEN**
- Browser-to-browser WebRTC media: **NOT YET PROVEN**
- `/me` browser-test rate-limit boundary: **REQUIRES INVESTIGATION**
- External provider/storage recovery: **NOT YET PROVEN**


## 2026-10-06 — Study Hub study-time architecture locked for implementation

The Study Hub study-time design has been documented in `designstudytime.md` and is now the implementation baseline.

### Locked principles

- Study Hub is tracked as **one learning-activity system per student/session**, not one authoritative timer per document.
- Documents, pages, and features remain context for validation/analytics.
- Switching documents or features must not reset or create a second authoritative Study Hub clock.
- Browser-local accumulation is preferred over frequent server heartbeats.
- Normal synchronization should be low-frequency (approximately hourly at most), with earlier flushes on inactivity, leaving Study Hub, tab visibility changes, navigation where reliable, and reconnect.
- Synchronization must be replay-safe/idempotent because a response can be lost after PostgreSQL commits.
- PostgreSQL remains the durable source of truth.
- Redis must not become the authoritative study-time store.
- The server remains authoritative for authentication, context validation, Nairobi calendar boundaries, replay protection, and the existing daily anti-gaming ceiling.
- Global product activity and Study Hub learning time must remain separate concepts.
- Existing local Study Activity accumulation should be reconciled and simplified rather than creating another timer system.

### Current repository evidence

The existing frontend already has a persistent Study Activity accumulator in `frontend/src/offline/studyActivity.ts`, including Nairobi date keys, visibility/interaction checks, local totals, synced totals, server baselines, and offline synchronization.

The existing backend already has aggregated StudyTimeLog storage and server-side controls. The remaining work is therefore primarily **architecture reconciliation**: consolidate the activity producers, make Study Hub one global learning clock, and align the server synchronization contract with safe longer batching.

### Important economics boundary

Study-time tracking must not become a client-authoritative entitlement mechanism. Free/Plus/Pro AI economics remain server-authoritative and continue to use the existing tested entitlement/quota contracts.

### Release-gate requirement

Do not call this design implementation-green until tests prove document switching, feature switching, inactivity, offline/reconnect, duplicate sync, lost-response retry, Nairobi midnight, daily ceiling, concurrent sync, authorization, and a 400-active-student load scenario.


## 2026-10-06 — Study Hub single-clock implementation pass

Implemented directly on `main`:

- Replaced the per-document/20-second Study Hub heartbeat with `POST /study-time/sync` using an absolute daily Study Hub total.
- Added browser-persistent single Study Hub accumulation with a maximum normal flush interval of about one hour plus earlier lifecycle/inactivity/reconnect flushes.
- Removed the document-owned timer from `PdfStudyCanvas` and the native document reader's 20-second heartbeat.
- Retired the old heartbeat endpoint with HTTP 410.
- Added concurrency-safe reconciliation by locking the authenticated user's PostgreSQL row before the Study Hub row is read/created/updated.
- Added migration `20261006_study_hub_time.sql` to preserve historical totals while consolidating old per-feature rows into one `study_hub` row per user/day.
- Added `scripts/test_study_time_runtime.py` covering monotonic replay-safe sync, daily ceiling, one-row storage, concurrent reconciliation, auth/CSRF, and legacy heartbeat retirement.
- Kept product analytics separate and cached its CSRF token to avoid repeated `/me` requests.

### Verification status

**Not green yet.** The implementation has been committed, but the local Docker verification gate still needs to run. Required next checks: migration apply/verify, Study Hub runtime pytest, TypeScript/Vite build, full `tools/run_local_qa.py`, and browser regression where applicable. Do not treat the design as frozen until these pass.


## 2026-10-06 — Study Hub single-clock implementation pass

Implemented directly on main: replaced the per-document/20-second Study Hub heartbeat with POST /study-time/sync using an absolute daily Study Hub total; added browser-persistent single Study Hub accumulation with low-frequency and lifecycle-triggered flushing; removed document-owned timers; retired the old heartbeat with HTTP 410; added PostgreSQL concurrency-safe reconciliation by locking the authenticated user's row; added migration 20261006_study_hub_time.sql to consolidate historical per-feature rows into one study_hub row per user/day; added scripts/test_study_time_runtime.py for replay safety, daily ceiling, one-row storage, concurrency, auth/CSRF, and legacy endpoint retirement; retained product analytics separately and cached its CSRF token.

### Verification status

**Not green yet.** Required next checks: migration apply/verify, Study Hub runtime pytest, TypeScript/Vite build, full tools/run_local_qa.py, browser regression, and later 400-active-student performance testing.


## 2026-10-06 — Study Hub regression audit and CI gate

### Regression findings

The Study Hub implementation exposed a missing CI protection boundary. `scripts/test_study_time_runtime.py` existed, but no GitHub Actions workflow executed it. The existing realtime runtime workflow tests realtime/calling/chat behavior and uses SQLite; that is insufficient for validating the PostgreSQL row-locking contract required by Study Hub reconciliation.

A real startup regression was also introduced during the runtime DDL removal in `chat_interactions.py`: the change removed the `app` import even though Flask request hooks still referenced `app`. This produced `NameError: name 'app' is not defined` and caused `prepza-app-1` to restart. Commit `18ed81a` restored only the required Flask app import; runtime schema mutation remains removed.

The Study Hub auth/CSRF test then exposed a route decorator-order mismatch. `require_csrf` executes before the route body, so the old route returned `403` before its internal `401` authentication check. The route is now explicitly protected with `@login_required` before `@require_csrf`, making the expected unauthenticated response deterministic.

### CI hardening

Added `.github/workflows/study-hub-runtime-regression.yml`, using PostgreSQL 17, canonical Alembic `upgrade head`, and `scripts/test_study_time_runtime.py`. This makes the Study Hub runtime/concurrency gate a CI regression test rather than a local-only check.

### Current verification state

- App container: **healthy/running** after the `app` import correction.
- pytest: **8.4.2 installed** in the current QA container.
- Previous Study Hub runtime results before the auth/CSRF fix: first four tests passed; fifth failed with `403 != 401` rather than hanging after runtime DDL removal.
- Corrected route has not yet been rerun through the full six-test suite.
- CI workflow has been added but has not yet completed for the new commit.

**Release gate remains NOT GREEN.**

## 10. 2026-10-06 — Study Hub focused runtime gate

The canonical Study Hub runtime regression script is now an executed release-gate test rather than merely an implementation check.

Command:

    docker compose -f docker-compose.vps.yml exec app python -m pytest scripts/test_study_time_runtime.py -vv -s

Latest result:

    6 passed, 3 warnings in 4.47s

The six cases prove:

1. absolute daily sync is monotonic and replay-safe;
2. the server enforces the 12-hour daily ceiling;
3. Study Hub uses one aggregate `study_hub` feature row rather than document rows;
4. concurrent reconciliation does not double-credit the same underlying total;
5. authentication and CSRF fail closed;
6. the legacy per-document heartbeat is retired.

The concurrency case runs against PostgreSQL row-locking semantics. The warnings are non-blocking `datetime.utcnow()` deprecation warnings.

### Study Hub release-gate boundary

This does **not** yet prove the complete browser/offline lifecycle. Still outstanding are browser visibility/inactivity behavior, reload/reconnect reconciliation, offline accumulation/reconnect, and the final browser QA pass.

### Current focused runtime inventory

| Gate | Latest evidence | Status |
|---|---|---|
| Full local QA | 74 passed, 0 failed, 3375 warnings | GREEN |
| Focused realtime runtime | 9 passed in 2.98s | GREEN |
| Focused calling runtime | 4 passed in 3.31s | GREEN |
| Redis chat-worker | real Redis event consumed/acknowledged | GREEN |
| Redis cross-process client delivery | real Socket.IO client received `chat:message` | GREEN |
| Study Hub runtime | 6 passed, 3 warnings | GREEN |
| Browser WebRTC media | not yet completed | NOT YET PROVEN |
| Browser/offline Study Hub lifecycle | not yet completed | NOT YET PROVEN |
| Storage/backup/restore | not yet completed | NOT TESTED |


## 8. Current release-gate evidence — 2026-10-07

This section supersedes older pending snapshots where later evidence exists.

### Green evidence
- Full disposable PostgreSQL/Alembic QA: 74 passed, 0 failed.
- Study Hub PostgreSQL runtime reconciliation: 6 passed, 3 warnings.
- Focused realtime runtime: GREEN.
- Focused calling signaling runtime: GREEN.
- Redis-backed chat worker/cross-process delivery: GREEN.
- Production-style Docker frontend/app build: GREEN.
- Browser-to-browser WebRTC media: GREEN — both authenticated browsers reached Connected and both received live remote audio MediaStream tracks through the real UI/signaling path.

### Remaining release gates
- E2EE identity lifecycle: NOT CERTIFIED; observed different-key /keys/register 409 requires lifecycle tests.
- Personal streak: PARTIALLY CERTIFIED; core Study Hub integration is green, but milestone/date-boundary/XP idempotency needs dedicated regression.
- Shared Streak: NOT RELEASE-CERTIFIED pending scope/wiring/canonical migration/runtime tests.
- Browser/offline Study Hub lifecycle: NOT TESTED.
- Storage backup/restore: NOT TESTED.
- Cross-system integration journeys: NOT TESTED.
- Current CI workflow execution after latest release-gate changes: NOT YET VERIFIED.
- Full clean-environment freeze regression: NOT TESTED.
- 400-user performance: DEFERRED until functional/browser/recovery gates are green.

### Repeatability rule
For future releases, the feature trace in qa/release_manifest.json must be updated with every release-scoped feature. scripts/qa_trace.py is a structural gate only; a feature becomes GREEN only after its declared runtime/browser/integration evidence and CI evidence pass.


## 2026-10-07 — Release-gate status reconciliation

The repeatable QA registry is now backed by `qa/release_status.json`, which records the current state of every tracked release gate and prevents historical snapshots from being mistaken for current status.

### Newly confirmed evidence
- Browser-to-browser WebRTC/media: **PASS** — clean two-browser run reached Connected on both sides and both browsers observed live remote audio MediaStream tracks through the real UI/signaling path.
- Study Hub PostgreSQL runtime: **PASS** — 6/6 tests passed; 3 non-blocking `datetime.utcnow()` deprecation warnings remain.
- Production-style Docker app/frontend build: **PASS**.

### Still open
- E2EE identity lifecycle: **IN PROGRESS**. The observed `/keys/register` 409 is an intentional different-identity conflict and is not a WebRTC failure; dedicated first-device/reload/restart/second-device/restore tests are still required.
- Personal streak: **IN PROGRESS**. Core Study Hub integration is exercised, but milestone/date-boundary/XP idempotency needs dedicated regression.
- Shared Streak: **IN PROGRESS**. Existing code is not yet release-certified; wiring, canonical schema ownership, frontend exposure and lifecycle/concurrency tests must be resolved.
- Browser/offline Study Hub lifecycle: **NOT TESTED**.
- Storage backup/restore: **NOT TESTED**.
- Cross-system journeys: **NOT TESTED**.
- Latest CI workflow execution: **NOT TESTED/NOT YET VERIFIED**.
- Final clean regression/freeze: **NOT TESTED**.

The 400-user performance gate remains deliberately deferred until the functional, browser and recovery gates are green.

## 2026-10-07 — E2EE identity gate test-defect correction

The first execution of the new E2EE identity lifecycle gate exposed **test-harness defects**, not a confirmed application failure:

- The backend runtime fixture was module-scoped, so the first test registered a primary user's key and the later peer-visibility test reused that same user, correctly receiving the application's intentional `409 IDENTITY_KEY_REPLACEMENT_REQUIRED` response.
- The cleanup test opened an explicit transaction on a SQLAlchemy session that already had an implicit transaction, producing `InvalidRequestError: A transaction is already begun on this Session.`
- The browser lifecycle test hit a Chromium `ERR_ABORTED` while waiting for `domcontentloaded` during reload, after the first identity registration had already passed.

The gate was corrected without changing E2EE application behavior: runtime cases now receive isolated users, cleanup uses the session's existing transaction lifecycle, and the browser reload waits for navigation commit before checking persistence. The gate remains **IN PROGRESS** until the corrected tests are executed on the rebuilt local stack.


## 2026-10-07 — Offline document and generated-artifact persistence gate prepared

A deeper browser gate has been added as `scripts/test_browser_study_hub_offline_content.py`. It is intentionally separate from the Study Hub clock/offline-lifecycle gate.

The new gate is designed to prove, in a real Chromium session:

- three independent Study Hub documents survive offline storage and reload;
- the stored document bytes are real PDF Blobs and the native offline reader opens them;
- summary, flashcards, quiz, and mind-map artifacts open from the offline generated-material store for **each** saved document;
- podcast metadata resolves to a local Blob-backed audio URL;
- offline replay does not issue generation POST requests;
- the configured offline storage caps remain exactly 75 MB/document, 250 MB total document assets, 80 generated-material rows, 512 KiB per generated payload, 25 MB per audio object, and 80 MB total audio cache.

During source inspection, the gate exposed a real offline artifact replay defect in the existing implementation: the selected material id was read from `sessionStorage` only after the offline generation branch had already checked it, and Study Hub package saving used the `/documents/<id>/materials/<id>` cache path without that path being accepted by the generated-material store. Podcast offline replay also lacked a cached playback descriptor.

Those application defects were fixed directly on `main` before the new gate was declared ready:
- `ca6b638` — selected Study Hub material is resolved before offline generation replay;
- `1969e14` — generated-material endpoint payloads are accepted by the offline store;
- `ecd4a8d` — podcast offline playback metadata is persisted alongside the audio Blob.

The browser gate itself is **NOT YET EXECUTED**. It is now the required local test before the broader offline-content/artifact gate can be marked PASS.


### 2026-10-07 — First execution exposed a real shared IndexedDB schema defect

The first local execution of `scripts/test_browser_study_hub_offline_content.py` reached browser IndexedDB seeding and failed with:

`Page.evaluate: NotFoundError: Failed to execute 'transaction' on 'IDBDatabase': One of the specified object stores was not found.`

Inspection showed that `prepza-offline-v2` used the same version number in two modules, but `studyHubOffline.ts` created only `savedStudyHub` while `generatedMaterials.ts` expected `generatedMaterials` and `generatedAudio`. Because IndexedDB does not run another upgrade when opening the same version, first-use order could leave stores absent.

The application was corrected on `main` with a version-4 migration. The v4 upgrade creates all three shared stores in either module, so both a fresh database and an existing broken v3 database converge on the same schema. The browser gate itself was not weakened.

Current state: **NOT YET EXECUTED after the fix**. Rebuild the Docker app before rerunning the browser gate so Chromium receives the corrected frontend bundle.


## 2026-10-07 — Admin Study Hub browser gate first execution

Command executed:
`docker compose -f docker-compose.vps.yml exec app python -m pytest scripts/test_browser_admin_study_time.py -q -s`

Result: **4 failed, 1 passed, 1 teardown error**.

The run did not certify the gate. Source review traced the four value mismatches to test-isolation assumptions: `/admin/operations` intentionally aggregates Study Hub seconds across all non-admin students, while the test assumed an empty surrounding student population. The daily 12-hour ceiling assertion also incorrectly treated a per-student ceiling as a global admin aggregate ceiling.

The teardown error traced to fixture cleanup ordering around the deliberately non-cascading `user_key.user_id` foreign key. The test now commits fixture-owned `UserKey` deletion before deleting fixture users.

The corrected gate compares fixture contributions against live admin baselines and still requires exact per-student equality, concurrency idempotency, Nairobi day-boundary correctness, admin exclusion, and cleanup. Evidence remains **IN PROGRESS** until the corrected run passes cleanly.


## 2026-10-07 — Admin Study Hub browser rerun still blocked at frontend document navigation

The corrected `scripts/test_browser_admin_study_time.py` was executed from the temporary Docker QA container against `http://app:5000`.

Command result: **1 passed, 4 failed** in 240.41s.

All four failures occur inside `browser_login()` at `page.goto(BASE_URL + "/", wait_until="commit")`, with Chromium timing out after 30 seconds. The POST `/login` immediately before navigation succeeds, so the failure is not currently evidence of a Study Time reconciliation, entitlement, admin aggregate, concurrency, Nairobi-boundary, or isolation regression.

The first attempted test still passes because it does not require browser navigation. The four browser-dependent cases do not reach their Study Time assertions.

Source inspection confirms the root route is the Flask `/` handler serving the built frontend `index.html`. The next diagnostic is therefore to isolate the HTTP response from the browser navigation path before changing Study Time logic or weakening the gate.

**Gate status remains IN PROGRESS.** Do not mark this gate PASS or convert the timeout into a product failure until the root-document navigation path is explained and the four blocked cases execute their actual assertions.

## 2026-10-08 — Admin Study Hub browser gate cleared

The browser authentication/navigation defect was isolated to the test running Chromium against the internal Docker hostname `http://app:5000`. The corrected gate now follows the same proven browser-login pattern as the other real-browser gates and uses `http://localhost:5000`, allowing Chromium to accept the Flask Secure session cookie on the special localhost origin.

User-executed command:

    python scripts/test_browser_admin_study_time.py -q

Result:

    **5 passed in 117.11s**

All five cases reached their intended assertions. The gate now proves student/admin view agreement after reconnect reconciliation, concurrent sync does not double-credit, the 12-hour daily ceiling is identical in both views, the Nairobi day boundary is respected, and admin accounts are excluded while students remain isolated.

The earlier 1-pass/4-fail navigation result is historical and superseded. No Study Time production logic was weakened to obtain this pass.

**Gate status: PASS.**

## 2026-10-08 — Organisation economics discussion: backend metering is tested, full organisation journey is not

The organisation/opportunity backend is covered more deeply than the release-gate summary alone might suggest, but it is important not to overstate that evidence.

The disposable QA suite currently proves organisation-side behavior including:
- organisation opportunity creation and ownership;
- targeting by university/program/year/semester and profile changes;
- admin verification, review, approval and publishing;
- student visibility and outsider/tenant isolation;
- real organisation opportunity rate-limit behavior;
- prepaid B2B campaign metering and advertiser-balance protection;
- campaign pricing snapshots remain locked after funding;
- a qualifying feed impression is billed at the configured CPM economics;
- a qualifying click is billed at the configured CPC economics;
- replay of the same billable event is idempotent;
- student frequency caps prevent repeated billable delivery to the same student;
- campaign exhaustion stops further spend and reaches zero remaining balance.

The dedicated metering regression is `test_b2b_prepaid_metering_protects_advertiser_balance_and_locks_campaign_pricing`. Its tested examples include KES 350 CPM producing 35 minor units for one qualifying impression, KES 20 CPC producing 2000 minor units for one qualifying click, and a KES 350-funded campaign exhausting after 1000 qualifying impressions.

**What this does NOT prove yet:** a complete real-provider organisation journey from payment/provider success -> organisation funding -> campaign delivery -> student-facing opportunity -> advertiser deduction across all external boundaries. Paystack/provider behavior is tested separately as a contract/idempotency layer, but controlled external-provider verification and the broader cross-system journey remain release gates.

**Ambassador routes are also not currently a separate release gate in this ledger.** If ambassador functionality is launch-scoped, it must receive a dedicated gate covering route authorization, referral attribution, the intended commission calculation, payout eligibility/balance, duplicate/failure/refund handling, and the complete referral -> paid student -> commission -> payout-eligibility journey. Until such a gate is executed, do not claim ambassador flows are release-certified.

## QA operating protocol — read this before changing, testing, or diagnosing anything

This section is an operational reminder for future QA work. **Do not skip it just because a command looks simple.**

### 1. Start from repository evidence, not assumptions
- Check the current main commit before deciding what is already verified.
- Read this file and qa/release_status.json before choosing the next gate.
- Treat the latest **executed evidence** as authoritative; older failures may be historical and superseded.
- Inspect the actual test runner/script before inventing a new command or environment.
- Never infer that a feature is green merely because related code or a test exists.

### 2. Never run destructive QA against the normal application database
- **prepza** is the normal local application database.
- **prepza_qa** (or another database ending in **_qa**/**_test**) is the disposable QA database.
- A temporary Docker container is **not** the same thing as a temporary database.
- Broad QA must use **tools/run_local_qa.py**, which creates/uses the disposable QA database, applies canonical Alembic migrations, switches DATABASE_URL, and then runs the suite.
- If a QA safety guard says it is connected to **prepza**, **stop and fix the environment**. Never disable or bypass that guard.
- Do not manually point the broad suite at **prepza** just to make a test run.

### 3. Git Bash + Docker path rule on Windows
When running a temporary QA container from Git Bash, use the MSYS path-conversion protection:

    MSYS_NO_PATHCONV=1 docker compose -f docker-compose.vps.yml run --rm --no-deps -v "$(pwd):/workspace" -w /workspace app sh -lc '...'

Without **MSYS_NO_PATHCONV=1**, Git Bash can rewrite **/workspace** into a Windows Git installation path such as **C:/Program Files/Git/workspace**, causing a Docker working-directory error.

### 4. Keep production and QA environments separate
- Do not install test dependencies into or permanently enlarge the production image just to run QA.
- Prefer the disposable QA container for pytest/test dependencies.
- Do not weaken production security settings to make a browser test pass.
- In particular, do not change a production Secure session cookie to non-Secure merely because Chromium is being run against an internal Docker hostname.

### 5. Browser QA must use a proven browser-origin pattern
- Compare a failing browser gate with existing browser gates before changing application logic.
- If Flask uses a Secure session cookie, remember that **http://localhost:5000** is a special browser origin; an internal hostname such as **http://app:5000** can behave differently.
- Prefer the already-proven browser login/navigation pattern used by other Prepza browser gates.
- Fix the test environment/origin when the evidence shows an environment mismatch; do not weaken application authentication/security to accommodate it.

### 6. Diagnose failures in layers
When a command fails, identify which layer failed before changing code:
1. shell/command syntax;
2. Docker/Compose/container creation;
3. dependency installation;
4. database/environment selection;
5. migration/schema setup;
6. test harness/fixture;
7. application backend;
8. browser/frontend;
9. external provider/network;
10. CI/deployment.

A failure at an earlier layer is **not evidence of a product regression at a later layer**.

### 7. Do not convert blocked tests into false failures or false passes
- A test that never reaches its intended assertion is not a valid product-failure diagnosis.
- A partial pass does not certify the whole gate.
- Record the exact result and why the gate is blocked.
- When a later run passes after a harness/environment correction, explicitly mark the earlier evidence as historical/superseded.
- Do not weaken assertions, remove safety checks, mock away real authentication/database behavior, or change production behavior merely to obtain green output.

### 8. Keep release evidence synchronized
For every meaningful release-gate run, record:
- date;
- exact command;
- current commit;
- exact pass/fail count;
- important warnings;
- whether the result is local, disposable QA, browser, CI, or external-provider evidence;
- what the test proves;
- what it does **not** prove;
- next gate.

Update qa/release_status.json when the release status changes. Do not mark a gate PASS without actual execution evidence.

### 9. Work directly on main, but make focused changes
- Prepza release work is done directly on **main**; do not create branches/PRs unless explicitly requested.
- Make the smallest focused change that fixes the demonstrated problem.
- Avoid unrelated refactors during release freeze.
- Do not create unnecessary commits; a coherent fix plus its required regression test/documentation is preferable to many tiny commits.

### 10. The default workflow for the next QA task
Before giving the user a command:
1. inspect the relevant runner/test and its environment assumptions;
2. confirm which database it will use;
3. confirm whether the command is safe for the normal **prepza** database;
4. choose the existing repository QA bootstrap when one exists;
5. run the narrowest relevant gate first;
6. if green, run the broader gate;
7. record the evidence immediately;
8. only then move to the next release gate.

**Core rule:** temporary container != temporary database. Use the repository's disposable QA bootstrap, preserve production security, diagnose the failing layer first, and record evidence before declaring anything green.


## 2026-10-08 — Full disposable QA rerun after admin-security changes

User-executed command used the repository's canonical disposable QA runner from a temporary Docker container.

Result:

    **82 passed, 3192 warnings in 42.90s**

The runner confirmed:

- existing **prepza_qa** was reused safely;
- Alembic **upgrade head** completed successfully;
- the full runner completed without test failures;
- the newly added centralized admin authorization/security matrix tests passed;
- organisation authorization, economics/entitlement, AI, realtime/E2EE, and personal-streak cases in the runner passed.

The warnings are non-blocking deprecation/legacy API warnings, primarily **datetime.utcnow()** and one SQLAlchemy **Query.get()** warning.

This is disposable PostgreSQL/Alembic QA evidence. It does **not** replace browser, external-provider, migration-rehearsal, cross-system, or final clean-environment release gates.

**Latest full disposable QA gate: PASS — 82/82.**


## 2026-10-08 — Offline content browser gate exposed a second test-harness IndexedDB fixture inconsistency

User-executed command:

    python scripts/test_browser_study_hub_offline_content.py -q

Result: **BLOCKED in the test fixture before the intended browser assertions**.

Chromium failed during `seed_offline_content()` with:

    NotFoundError: Failed to execute 'transaction' on 'IDBDatabase': One of the specified object stores was not found.

Source comparison against the production offline modules and the already-working browser gates showed the problem was in the test fixture, not PostgreSQL, Flask, or the browser product path. The fixture opened the shared `prepza-offline-v2` database three times concurrently at version 3, with each opener responsible for creating only one store. Because `savedStudyHub`, `generatedMaterials`, and `generatedAudio` are stores in one shared database, concurrent first-open upgrade handlers could leave one opener without another store when it immediately started its transaction.

The production implementation is different: `generatedMaterials.ts` and `studyHubOffline.ts` now use the shared v4 schema and create the required stores during the v4 upgrade. The test fixture has therefore been corrected to open the shared database once at version 4, create all three stores in one upgrade handler, then seed them sequentially. The separate document-asset database is also opened once and seeded after its own schema creation.

This result is **not evidence of a production regression**. It is evidence that the browser QA fixture was not faithfully modelling the production IndexedDB schema lifecycle. The earlier production IndexedDB v3 migration defect remains a real historical production-impacting issue and is already fixed; this newly found fixture defect is test-only.

**Gate status remains: NOT TESTED / BLOCKED.** The corrected fixture must be executed before the offline content/artifact browser gate can be marked PASS.

**Important production-impact classification from this run:**
- Host-Python fixture connecting to `127.0.0.1:5432`: **test harness only**, not production.
- Shared IndexedDB seed race/missing-store error: **test harness only**, not production.
- Earlier v3 shared IndexedDB migration defect discovered during this same gate preparation: **real production-impacting defect, already fixed and requires the browser gate to verify the deployed frontend migration path**.

    
## 2026-10-08 — Offline content browser gate: Study Hub navigation timeout after fixture correction

User-executed command:

    python scripts/test_browser_study_hub_offline_content.py -q

Result:

    PASS: multiple saved documents remain listed offline
    FAIL: Locator.wait_for: Timeout 15000ms exceeded
    waiting for get_by_role("button", name="Continue Reading", exact=True) to be visible

This run reached the offline My Study list successfully, so the earlier IndexedDB fixture corrections were exercised far enough for the three saved documents to render. It then timed out while the test attempted to enter the selected document's Study Hub. Source inspection of the current production UI confirms that the document row is a button and that the Study Hub component renders the production "Continue Reading" button before entering the native offline reader.

The test has therefore been corrected to target the actual document-row button and, if "Continue Reading" still fails, print the complete rendered body so the next run identifies the screen/state actually reached. This is intentionally a test-only diagnostic change. The timeout is not yet classified as a production defect because the intended reader assertions ("OFFLINE" and "Offline study copy") were never reached.

**Gate status remains: NOT TESTED / BLOCKED.** The next execution must use the corrected test and its diagnostic output, if needed, before deciding whether any production navigation/offline logic is implicated.

## 2026-10-08 — Offline content gate: document iteration returned to the wrong UI level

User-executed command:

    python scripts/test_browser_study_hub_offline_content.py -q

Result:

    PASS: multiple saved documents remain listed offline
    FAIL: waiting for locator("button").filter(has_text="Offline Economics Notes").first

The failure is a test navigation bug. The production offline reader Back control returns to the selected document Study Hub. The test then immediately tried to find document-row buttons, which exist on the parent Study Materials screen.

The test is now corrected to follow the real UI path after each offline reader assertion:

    offline reader -> Back -> document Study Hub -> My Study -> document list

This does not change production offline behavior and does not generate any materials. The generated-material portion seeds already-ready artifacts, opens them through the real replay UI while offline, and asserts that no generation POST is sent.

Gate status remains NOT TESTED / BLOCKED until the corrected browser script is executed.


## 2026-10-10 — Offline content/artifact gate: execution context destroyed during fixture seeding

User-executed command against a rebuilt app image at `4f1ed663`:

    python scripts/test_browser_study_hub_offline_content.py -q

Result:

    FAIL: Page.evaluate: Execution context was destroyed, most likely because of a navigation

This exception occurs inside `seed_offline_content()`, before the browser asserts that saved materials can be replayed. It is therefore **not yet evidence of an offline-artifact product failure** and does not satisfy the gate.

Source inspection found a specific startup navigation path that could interrupt the asynchronous IndexedDB fixture: `frontend/public/sw.js` calls `skipWaiting()` during install and `clients.claim()` during activation; `frontend/public/sw-register.js` reloads the page on every `controllerchange`. The test previously waited only 1.2 seconds after navigation before starting a multi-store IndexedDB seed. The corrected test records main-frame navigations, requires the same-origin startup reload and a controlled service worker to be established, and waits for the real Home UI instead of relying on that fixed delay. This expected lifecycle is now explicitly checked by the test rather than silently assumed; the next run will confirm whether the observed runtime sequence matches the source path.

The same source audit found an independent **production offline-replay defect**. Summary, Flashcards, Practice Questions and Mind Map first requested `/me`; an offline failure there prevented the offline-aware `generationRequest()` from running. In addition, `summary` was not normalized to the `/summarize` feature name, and the offline response key did not match the Summary screen's expected `summary` property. The application now resolves the exact selected, ready material from IndexedDB before any network generation call, normalizes these feature names and returns an error instead of falling through to a generation POST when offline material is unavailable. The fixture's Mind Map branch shape was also corrected to match what the renderer consumes.

**Gate status remains: NOT TESTED / BLOCKED.** These changes are on main but have not yet been executed. Rebuild the app image and rerun the gate; only the full run can prove each material screen, podcast Blob playback, zero generation POSTs and offline reload persistence.


## 2026-10-10 — Offline artifact gate redesigned around verified cache contracts

The last user-executed browser run was against commit `4f1ed663` and stopped during the asynchronous IndexedDB fixture seed with:

    FAIL: Page.evaluate: Execution context was destroyed, most likely because of a navigation

That failure occurred before any intended artifact assertion. It does not establish that offline replay failed.

Source inspection then identified two product/harness issues that are now addressed on `main`:

1. `generationRequest()` previously saved the UI response from a generation endpoint (for example `{material_id, reused, summary}`) under the canonical offline-material path. The real GET `/documents/<id>/materials/<material_id>` returns a different shape: `{material_id, type, status, parameters, payload}`. The app now resolves and saves that canonical response only after checking that the exact ready artifact is private and owned by the current student. Shared Library material is not promoted into an offline entitlement.
2. A ready podcast could play without necessarily leaving both its descriptor and the audio Blob available offline. The player now best-effort caches the selected private podcast artifact, the ready audio descriptor, and its fetched audio Blob.

The browser gate itself has also changed so it no longer fakes the generated-material cache. It seeds only the saved source-document package and creates ready private `GeneratedMaterial` rows in the test fixture database. The real UI then opens each existing material while online; exact-material reuse requests must carry `X-Prepza-Material-ID`. A Playwright request guard blocks any material-generation POST missing that ID before it can reach Flask and potentially enqueue AI work. Podcast readiness/audio are stubbed at the browser HTTP boundary, so the gate does not call OpenAI or a GPU service. The test then goes offline and verifies that the actual cache written by Prepza can reopen Summary, Flashcards, Practice Questions, Mind Map and Podcast, survives a browser reload, and triggers no generation POST while offline.

The startup fixture waits for the service-worker control/reload described by `frontend/public/sw.js` and `frontend/public/sw-register.js` rather than relying on the earlier fixed 1.2-second delay. The generation-route guard also matches digit-only document IDs; this pattern was checked against the actual request paths.

**Verification status:** source changes are on `main`; GitHub's Python-syntax and prior frontend-build checks have passed on preceding commits, but the newest guarded test change has not yet been executed by the user in a local browser. Rebuild the app image and rerun `scripts/test_browser_study_hub_offline_content.py -q`. Do not mark this release gate PASS until the complete online-cache -> offline replay -> reload assertions complete.


## 2026-10-10 — Preserve the underlying offline browser startup exception

The latest reported run still stops in `login()`, before IndexedDB seeding and before any offline-artifact assertions. Its visible output recorded two main-frame navigations to `http://localhost:5000/`, but the helper wrapped the inner exception in a `RuntimeError` and the top-level runner printed only the wrapper message. That meant the actual wait/state failure was not visible in the concise test output.

Commit `12e5a901` changes diagnostics only: the wrapper now includes the underlying exception type/message and the current page URL. It does **not** increase timeouts, suppress the failure, or change service-worker behavior.

**Next verification:** rebuild the app image from current `main` and rerun `scripts/test_browser_study_hub_offline_content.py -q`. Capture the new `underlying=...` detail. Use that evidence to identify the failing wait/state transition before changing behavior.

**Gate status: NOT TESTED.** No artifact, offline replay, zero-generation-POST, podcast-Blob, or offline-reload assertion has yet passed in this run. This diagnostic commit is not a browser-test pass.


## 2026-10-10 — Diagnose an uncontrolled service-worker page

**Observed result:** The updated offline browser test still fails before IndexedDB seeding with `supported: true` and `controlled: false`, after two main-frame navigations to `http://localhost:5000/`. This confirms the browser exposes the Service Worker API, but it does not establish that `/sw.js` registered, installed, activated, or claimed the page. It is not evidence of an external-provider outage.

**Diagnostic follow-up:** Commit `8022890ef729824b8156c5f26dfca9375c3d6f03` adds failure-only evidence for current registrations and their worker states, root service-worker asset HTTP responses, and related browser console/request errors. This instrumentation does not alter the app's service-worker behavior or relax the assertion.

**Gate status: NOT TESTED / BLOCKED.** The next run must identify whether registration is absent, script delivery/installation failed, or an active worker did not claim the page. Do not proceed to offline artifact assertions or mark this gate PASS until the root cause is addressed and the complete test passes.


## 2026-10-10 — Chromium-level service-worker lifecycle diagnostics

**New evidence from the latest local run:** `/sw-register.js` and `/sw.js` both return HTTP 200 with JavaScript content types; neither request failed. A root-scope registration exists, but `installing`, `waiting`, and `active` are all null at the time of inspection, and the page has no controller. The same-origin page had two navigations. This narrows the failure to an unobserved service-worker lifecycle/registration state rather than missing static files, but it does not yet establish the root cause.

**Diagnostic follow-up:** Commit `3f28284f2cffb3e67c07923284decf43e75f1687` listens to Chromium DevTools Protocol service-worker error, registration-update, and version-update events before navigation. It also captures page-level uncaught errors. These are diagnostic-only changes; they do not alter worker registration or bypass the control assertion.

**Gate status: NOT TESTED / BLOCKED.** The next run should reveal worker parse/install errors or show which lifecycle states Chromium reports. Do not mark the offline artifacts gate PASS until the worker is active and the end-to-end offline content test completes.
