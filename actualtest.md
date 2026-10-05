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

- **71 test functions** named `test_...`
- **74 collected pytest test cases**
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

### B. `tests/test_route_security_matrix.py` — 2 test functions

16. **`test_every_admin_get_route_rejects_anonymous_and_non_admin_users`**
    - Enumerates admin GET routes.
    - Verifies anonymous users and ordinary students cannot access them.

17. **`test_every_admin_mutation_fails_without_csrf_for_all_non_admins_and_admin`**
    - Enumerates admin state-changing routes.
    - Verifies missing/invalid CSRF protection is rejected for the security boundary.

### C. `tests/test_authenticated_route_matrix.py` — 1 test function

18. **`test_every_get_route_dispatches_for_authenticated_student_and_admin`**
    - Exercises the GET route surface with authenticated student and admin identities.
    - Detects routes that look registered but fail at runtime.

### D. `tests/test_local_qa_authz.py` — 5 test functions

19. **`test_student_cannot_cross_organisation_boundary`**
    - Creates a second organisation.
    - Verifies one student cannot use another tenant's IDs to create or mutate resources.
    - This is an IDOR/horizontal authorization check.

20. **`test_student_cannot_cross_vertical_admin_boundary`**
    - Verifies an ordinary student cannot perform administrator-only operations.

21. **`test_logout_and_session_version_rotation_invalidate_old_session`**
    - Verifies logout and session-version rotation invalidate an old authenticated session.

22. **`test_suspended_account_cannot_continue_using_existing_session`**
    - Suspends an account.
    - Verifies an existing authenticated session no longer grants access.

23. **`test_state_changing_organisation_actions_require_csrf`**
    - Verifies organisation mutations require the expected CSRF token.

### E. `tests/test_frontend_ai_generation_contract.py` — 3 test functions

24. **`test_backend_generation_routes_and_payload_keys_match_contract`**
    - Verifies backend generation endpoints and response payload names match the expected contract.

25. **`test_active_frontend_generation_contract_matches_backend`**
    - Compares active frontend generation calls with backend route/payload expectations.
    - Catches frontend/backend naming drift.

26. **`test_frontend_usage_contract_uses_canonical_usage_endpoint`**
    - Verifies the frontend uses the canonical usage endpoint.

### F. `tests/test_ai_artifact_fingerprint.py` — 10 test functions

27. **`test_shared_identity_is_deterministic`**
    - Same generation identity inputs produce the same fingerprint.

28. **`test_parameter_order_does_not_change_identity`**
    - Reordering equivalent parameters does not create a different artifact identity.

29. **`test_parameters_change_identity`**
    - Meaningful generation parameter changes create a different identity.

30. **`test_prompt_and_schema_versions_change_identity`**
    - Prompt/schema version changes invalidate the old artifact identity.

31. **`test_shared_and_private_scopes_never_collide`**
    - Shared and private generation scopes cannot accidentally share identities.

32. **`test_private_identity_is_owner_specific`**
    - Private artifact identity includes the correct owner boundary.

33. **`test_scope_is_normalized`**
    - Scope values are normalized consistently.

34. **`test_private_requires_owner`**
    - Private generation cannot be created without an owner.

35. **`test_shared_rejects_owner`**
    - Shared generation cannot incorrectly carry a private owner identity.

36. **`test_invalid_scope_is_rejected`**
    - Unknown generation scopes are rejected.

### G. `tests/test_ai_generation_store.py` — 2 test functions

37. **`test_generation_lookup_shapes_are_explicit`**
    - Verifies generation lookup states have an explicit, usable shape.

38. **`test_only_owner_is_allowed_to_call_provider`**
    - Verifies only the generation owner/producer can reach the provider path.

### H. `tests/test_ai_economics.py` — 12 test functions

39. **`test_ada_unit_weights_are_locked`**
    - Locks the canonical Ada AI unit weights.

40. **`test_ada_units_round_up`**
    - Verifies AI unit calculations round up according to the economic contract.

41. **`test_plan_defaults_match_locked_entitlements`**
    - Verifies Free/Plus/Pro default limits match the locked product economics.

42. **`test_plan_patch_rejects_unknown_fields`**
    - Rejects unsupported plan fields.

43. **`test_plan_patch_rejects_negative_limits`**
    - Rejects negative quota/limit values.

44. **`test_plan_patch_accepts_feature_and_access_flags`**
    - Verifies valid feature/access flags can be patched.

45. **`test_offline_study_is_core_for_free`**
    - Verifies offline study is part of the Free entitlement.

46. **`test_admin_cannot_disable_offline_study`**
    - Protects the product contract from disabling the core offline feature.

47. **`test_paystack_plan_sync_updates_provider_when_price_drifts`**
    - Verifies provider plans are updated when the provider price is wrong.

48. **`test_paystack_plan_sync_does_not_write_when_already_matching`**
    - Verifies no unnecessary provider write occurs when the plan already matches.

49. **`test_paystack_plan_sync_requires_plan_code`**
    - Rejects provider synchronization without the required plan code.

50. **`test_student_offer_definition_is_monthly_and_plan_isolated`**
    - Verifies the student offer is monthly and plan-specific.

### I. `tests/test_ai_reusable_generation.py` — 13 test functions

51. **`test_normalize_parameters_is_deterministic_and_whitespace_safe`**
    - Canonicalizes generation parameters deterministically.

52. **`test_normalize_parameters_rejects_unknown_keys`**
    - Rejects unsupported generation parameters.

53. **`test_normalize_parameters_rejects_invalid_counts`**
    - Rejects invalid generation counts.

54. **`test_normalize_parameters_rejects_blank_strings`**
    - Rejects meaningless blank generation parameters.

55. **`test_normalize_parameters_rejects_unknown_material_type`**
    - Rejects unsupported artifact/material types.

56. **`test_empty_parameters_are_canonical`**
    - Verifies empty parameter sets have a canonical representation.

57. **`test_first_generation_calls_provider_and_second_identical_request_reuses`**
    - First request calls the provider.
    - Identical later request reuses the ready artifact instead of paying for another generation.

58. **`test_inflight_identical_request_attaches_without_provider_duplicate`**
    - Concurrent identical requests attach to the in-flight generation rather than duplicating provider work.

59. **`test_reused_ready_artifact_does_not_check_entitlement`**
    - Verifies a ready reusable artifact follows the intended reuse path without incorrectly re-consuming the generation entitlement.

60. **`test_flashcard_variant_pool_rotates_four_versions_before_reuse`**
    - Verifies four generation variants rotate before reuse.

61. **`test_all_document_materials_use_the_shared_four_variant_pool`**
    - Verifies summary, quiz, flashcards, podcast, and mind map use the shared variant-pool mechanism.

62. **`test_generation_request_ceilings_are_enforced`**
    - Parametrized over four material types:
      - summary: maximum 10 pages
      - podcast: maximum 50 minutes
      - flashcards: maximum 50 cards
      - mind map: maximum 50 nodes
    - This is the reason the 71 functions become 74 collected pytest cases.

63. **`test_generation_store_exposes_inflight_family_lookup`**
    - Verifies the generation store exposes the in-flight family lookup required for request coalescing.

### J. `tests/test_realtime_e2ee_runtime.py` — 8 test functions

64. **`test_socket_membership_and_same_conversation_delivery`**
    - Creates an E2EE direct conversation between student A and B.
    - Verifies both members can join.
    - Verifies the admin outsider is denied.
    - Sends an encrypted payload through the real HTTP message route.
    - Verifies the receiver gets the persisted encrypted message over realtime.

65. **`test_direct_e2ee_plaintext_is_rejected_before_persistence`**
    - Sends plaintext to a direct E2EE conversation.
    - Verifies HTTP 409.
    - Verifies plaintext was not persisted.

66. **`test_chat_retry_is_idempotent_and_does_not_duplicate_message`**
    - Sends the same client message twice.
    - Verifies the retry returns the same message identity rather than creating a duplicate row.

67. **`test_offline_receiver_recovers_from_database_history`**
    - Sends an encrypted message while the receiver is not connected to realtime.
    - Verifies the receiver can recover it from PostgreSQL chat history.

68. **`test_socket_session_version_and_suspension_are_enforced`**
    - Verifies a valid session can connect.
    - Rotates the user's session version and verifies the stale socket is rejected.
    - Suspends the user and verifies a new socket is rejected.

69. **`test_frontend_realtime_contract_matches_backend`**
    - Verifies frontend and backend agree on realtime event names and important Socket.IO behavior.
    - Checks credentials, reconnection, disconnect behavior, and offline client message IDs.

70. **`test_realtime_deployment_contains_dedicated_chat_worker`**
    - Verifies the production-style Compose stack contains the dedicated `chat-worker`.
    - Verifies Redis configuration and worker consumption/channel wiring.

71. **`test_redis_stream_queue_is_not_treated_as_postgres_source_of_truth`**
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
