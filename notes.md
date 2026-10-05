# Prepza Learning Notes

This file is the running learning record for building Prepza.

The goal is not only to record what changed, but also what I learned, why we made the design decision, what evidence proved it, and how I would explain the decision in a technical interview.

These notes should grow alongside the production-readiness audit so someone can later trace the learning curve from a working laptop setup to a deployable production system.

## 2026-10-04 — Starting the learning record

### 1. Docker: the basic idea

**What I learned**

Docker lets us run Prepza inside a controlled environment called a container. Instead of depending on exactly what is installed on my Windows laptop, the application and its runtime dependencies can be assembled into a repeatable environment.

For Prepza, Docker is especially useful because the real application is not just one Python file. It depends on Python packages, PostgreSQL, Redis, the Flask application, realtime services, and background workers.

Docker Compose lets us describe those pieces as services and start them together.

**How Docker helped me**

My laptop is Windows, while our production-style Linux containers run a Linux environment. Docker gives Prepza a consistent Linux-based runtime without me having to turn my whole laptop into a Linux computer.

Our local QA environment therefore gets much closer to the environment Prepza will actually run in.

### 2. The laptop 'superpower': virtualization

**What I learned**

Docker containers are lightweight, but on Windows they still need a Linux environment underneath them for Linux containers.

I enabled the hardware/software virtualization support needed by Docker Desktop. In simple terms, this lets my computer create and run virtualized environments efficiently.

This is different from saying that Docker creates a full virtual machine for every container. Containers share the underlying Linux kernel provided by Docker's Linux environment, which makes them much lighter than running a separate full operating system for every application component.

**Why this matters**

This is one of the reasons Docker Desktop can run Linux-based Prepza services on my Windows laptop.

### 3. Docker Compose: running Prepza as a small system

Instead of manually starting PostgreSQL, Redis, Flask, and the other pieces one by one, our Compose file describes the services and their relationships.

For the VPS-style setup we currently use:

- postgres = the database
- redis = realtime/event infrastructure
- app = the main web application
- realtime = the realtime Socket.IO service
- chat-worker = background worker that consumes chat events

A useful mental model is: Compose = the conductor; containers = the musicians.

The services need to work together, so Compose also handles their networking, startup dependencies, and environment configuration.

### 4. Why we rebuild before QA

Our standard local QA loop deliberately does this:

    git fetch origin
    git reset --hard origin/main
    docker compose -f docker-compose.vps.yml build app
    docker compose -f docker-compose.vps.yml up -d app
    docker compose -f docker-compose.vps.yml exec app python -m pip install -r requirements-test.txt
    docker compose -f docker-compose.vps.yml exec app python tools/run_local_qa.py

**Why**

The Docker image is a packaged snapshot of the application at build time. If code changes but the image is not rebuilt, I can accidentally test an older version.

So rebuilding is part of making the test result trustworthy.

### 5. A real production lesson from today's realtime QA

We fixed a test-fixture registration problem, but the next run revealed something more valuable: the test suite reached the real application and database and found actual integration defects.

The current run was: **69 passed, 5 failed, 3362 warnings.**

The failures are not five unrelated failures. Two important root causes appeared:

#### Root cause A — Flask application setup happens too late

The realtime tests import realtime_server after the Flask application has already handled a request.

realtime_server.py then tries to register routes through register_offline_activity_routes(app, db). Flask correctly rejects this because application route setup is supposed to happen before the app starts handling requests.

**Lesson:** application initialization order matters. A module that registers routes is part of application startup, not something we should lazily perform after requests have begun.

#### Root cause B — ORM model and database schema disagree

The SQLAlchemy model for message_attachment expects source_document_content_id, but the QA PostgreSQL database does not contain that column.

The database therefore raised psycopg2.errors.UndefinedColumn.

This is a classic **schema drift / migration reconciliation** problem: the Python code knows about a column that the database schema has not received.

The following retry/offline tests then inherited the aborted database transaction, which is why they produced InFailedSqlTransaction errors instead of exposing completely independent root causes.

**Lesson:** when debugging integration tests, look for the first database/application error before treating every later failure as a separate bug.

### 6. Why these failures are actually useful

A test that says 'the function exists' is weaker than a test that starts the application, talks to PostgreSQL, performs an authenticated operation, and discovers that the actual database schema is wrong.

This is why we are doing the production-readiness audit gate by gate.

We want evidence of:

frontend → HTTP/API → Flask → service logic → database/storage → realtime/worker infrastructure

rather than only evidence that individual files look correct.

## Interview-ready explanations

### Docker

> I used Docker to make Prepza's runtime reproducible. Instead of relying on my Windows host environment, I run the application and its infrastructure dependencies in defined Linux containers, with Docker Compose coordinating the services.

### Virtualization

> On Windows, I enabled the virtualization support Docker Desktop needs to run Linux-based containers efficiently. I learned that containers are not simply full VMs; they use a Linux environment and share its kernel, which keeps them lighter.

### Docker Compose

> I used Docker Compose to model Prepza as multiple cooperating services—PostgreSQL, Redis, the web app, realtime service, and a chat worker—so I can reproduce their networking and dependencies locally.

### Schema drift

> During integration testing, the SQLAlchemy model expected a column that the PostgreSQL schema did not have. That exposed schema drift. Rather than patching the test around it, I treat the migration history and ORM model as a contract that must reconcile before deployment.

### Integration testing

> I don't consider a feature production-ready just because unit or static tests pass. I want to exercise the real request path and infrastructure, because integration testing can reveal failures at the boundaries between the application, database, workers, and realtime system.

## Learning curve

### Stage 1 — Local environment
- Learned Git basics needed to synchronize the local working tree with main.
- Installed the local development tools needed by Prepza.
- Learned why Docker Desktop needs virtualization support on Windows.
- Learned the difference between a container and a full virtual machine.
- Learned how Docker Compose starts a multi-service application.

### Stage 2 — Production-readiness engineering
- Learned to use a disposable PostgreSQL QA database.
- Learned that Alembic migrations must bring the database to the expected schema.
- Learned to distinguish a root-cause failure from cascading transaction failures.
- Learned why realtime infrastructure needs explicit integration tests.
- Learned that an application's initialization order is part of runtime correctness.
- Learned that passing static tests is not enough to prove a production system works.

### Next things to learn
- How to reconcile the missing message_attachment.source_document_content_id migration.
- How Flask application initialization should be structured so routes are registered exactly once and before requests.
- How Socket.IO authentication and conversation membership work end-to-end.
- How E2EE messages move from the client to persistence and realtime delivery without storing plaintext.
- How Redis Streams and the chat-worker provide durable realtime event processing.
- How deployment rehearsal proves the production configuration matches what we tested locally.

## Rule for future notes

For every important change or discovery, add:
1. What happened
2. Why it mattered
3. What we changed
4. What evidence proved it
5. What I learned
6. How I would explain it in an interview

The notes are part of the project, not an afterthought.

## 2026-10-05 — Realtime/schema reconciliation in progress

### What we changed today

1. **Moved realtime route registration into application startup.**
   - `offline_activity_routes.py` and `e2ee_production_hardening.py` were being registered from `realtime_server.py`.
   - That was unsafe because `realtime_server.py` can be imported after Flask has already served a request.
   - Route registration now happens at the end of `app.py`, after the application's models and base routes exist.
   - `realtime_server.py` is now an entrypoint for Socket.IO behavior rather than a late route-registration mechanism.

2. **Added an Alembic schema reconciliation for chat attachments.**
   - The ORM already had `MessageAttachment.source_document_content_id`.
   - The verified SQL migration `migrations/20260926_chat_study_document_share.sql` also existed, but the disposable QA harness runs the Alembic chain and does not automatically execute the hand-managed SQL migration directory.
   - We added `alembic/versions/20261005_chat_attachment_source_document.py` so the Alembic-managed QA database receives the same column, foreign key, and index.
   - The migration is idempotent for the column, constraint, and index so fresh and existing databases can converge safely.

### Important lesson

**`alembic upgrade head: OK` does not automatically mean the runtime schema is correct.**

It only proves the migrations that Alembic knows about completed successfully. If an older migration system, manual SQL migration, baseline snapshot, or ORM change is outside that chain, the database can still disagree with the application.

For Prepza, we are therefore reconciling:
**ORM model ↔ baseline schema ↔ migration history ↔ actual disposable PostgreSQL database.**

### Current evidence

The previous QA run reached the real PostgreSQL-backed realtime tests and reported:
**69 passed, 5 failed, 3362 warnings.**

The two confirmed root causes were the late Flask route registration and the missing `message_attachment.source_document_content_id` column. The remaining transaction-aborted failures must be rerun after those root causes are fixed before being classified independently.

The fixes are committed directly on `main`. They are **not yet considered proven** until the standard Docker rebuild + test-dependency install + full QA loop passes.

### Interview-ready explanation

> I found a schema-drift problem during integration testing. The ORM and an existing SQL migration knew about a column, but the Alembic-managed disposable database did not. I traced the discrepancy across the baseline schema and migration systems and added an explicit Alembic reconciliation instead of modifying the QA database manually.

A second interview point:

> I also learned that Flask application initialization is part of correctness. Route registration belongs in application construction, before requests are handled, rather than in a secondary realtime entrypoint that may be imported later.

### Next verification

- Rebuild the application image.
- Reinstall the test requirements as part of the standard QA loop.
- Run the full real-world QA suite again.
- If the five realtime failures disappear, separately verify the Redis-backed production realtime path before marking the realtime gate green.


## 2026-10-05 — Latest QA result and chat scaling lesson

### Latest standard QA evidence

The standard Docker QA loop was rerun from origin/main at commit 1297c66. The migration revision-ID problem is fixed: Alembic now reaches "Alembic upgrade head: OK". The full suite reached 70 passed, 4 failed, 3377 warnings in 41.92s.

Realtime/E2EE is therefore NOT GREEN yet.

The four failures currently reduce to three important areas:

1. Duplicate Flask routes: GET /study-time/offline-baselines and POST /study-time/offline-sync are each registered by two endpoint functions. This teaches that the final Flask url_map must be checked, not just individual route definitions.
2. Late Flask after_request setup: realtime_server.py still registers an after_request hook when imported after the app has already handled a request. Routes were moved into startup, but this hook is another form of late application setup. The correct lifecycle is: create/configure app -> register routes/hooks/extensions -> serve requests.
3. Plaintext E2EE enforcement: the direct E2EE endpoint accepted {"body": "THIS IS PLAINTEXT"} with HTTP 201 when the contract expects HTTP 409 before persistence. We must trace authentication -> membership -> E2EE validation -> persistence and find the bypass.

The two socket failures are symptoms of the same late after_request problem, so they should not be counted as two unrelated root causes.

### Alembic revision-ID lesson

The earlier migration failure happened because the revision ID was longer than the 32-character storage available to Alembic's version table. We shortened 20261005_chat_attachment_source_document to 20261005_chat_attach_source_doc. The new run reaching Alembic upgrade head: OK proves that specific migration bookkeeping failure is resolved.

### Future chat scaling design — not implemented yet

We should not delete the server copy of a chat message immediately after delivery. Delivery means a device received an event; it does not prove that the message is durably recoverable. A browser can crash, IndexedDB can be cleared or evicted, a device can be lost, or the user can sign in on another device.

The safer mental model is:

message -> PostgreSQL encrypted history + recipient device IndexedDB

PostgreSQL remains the durable source of truth. IndexedDB is the local cache/offline layer. A future encrypted backup should be created on the device and encrypted before leaving it; email can be a destination for ciphertext, not the chat database.

### Message partitioning, explained simply

Partitioning means splitting one very large logical message dataset into smaller physical sections so the database can manage it more efficiently. Think of one giant library being divided into labelled rooms. The application can still treat it as one logical collection.

A future time-based example could look like:

messages_2026_10
messages_2026_11
messages_2026_12
messages_2027_01

We should NOT choose the partition key just because it sounds scalable. First measure:

- messages created per day/month;
- average and percentile message/ciphertext size;
- total table and index storage growth;
- which history ranges users actually read;
- query latency as the dataset grows;
- which conversations are hot versus rarely accessed;
- backup and restore time.

Those measurements tell us whether partitioning is useful and what key makes sense. For example, if most reads are for recent messages, time-based partitions may fit well. If users constantly read very old conversations, aggressive time-based strategies may be less helpful.

### Archival, explained simply

Archival means moving old, rarely accessed data out of the hottest storage path while keeping it recoverable. Think of moving old books from the library's main room into a labelled storage room.

A future flow could be:

active PostgreSQL data -> measured age/access threshold -> colder/cheaper archive storage -> optional deletion after an explicit retention policy

Again, the threshold should be measured, not guessed. We should observe storage growth, access frequency, query latency, and backup costs before deciding something like "archive after 90 days."

### Partitioning versus archival

Partitioning mainly organizes a large database dataset into smaller pieces. Archival mainly moves cold data to a cheaper storage tier. They can be combined. Deletion is different: it permanently removes data under a defined policy.

### Why IndexedDB cannot be the only permanent chat store

Browser storage is useful for recent history and offline queues, but users can clear site data and browsers can impose storage limits. A good future design is to keep recent/frequently used history locally, keep unsent messages locally until the server confirms persistence, and fetch older history from the durable server store when needed.

### E2EE backup lesson

Do not email raw chat history. For an E2EE backup, encrypt the backup on the user's device before it is uploaded, emailed, or stored elsewhere. The backup destination should receive ciphertext. Key recovery must also be designed explicitly: if the only decryption key is lost with a device, the backup may be useless.

### Engineering principle learned

Scale architecture should be driven by measured workload, not fear of future scale. The sequence is: prove the current system -> launch/test -> measure volume, access patterns, storage and latency -> identify the real bottleneck -> choose partitioning, archival, object storage or retention policy -> load-test -> migrate carefully.

### Interview-ready explanations

**Why keep a server copy?** Delivery acknowledgement proves receipt of an event, not durable recoverability. I would keep encrypted server history as the durable source of truth and use IndexedDB as a local cache/offline layer.

**Partitioning:** I would partition a large message dataset only after measuring write volume, read patterns, index size, storage growth and query performance, then choose a partition key that matches the workload.

**Archival:** I would move cold, rarely accessed history to cheaper storage based on measured access and storage patterns while preserving a recovery path.

**E2EE backup:** I would encrypt the backup on the client before it leaves the device, so email or cloud storage only sees ciphertext, and I would design key recovery explicitly.

**Overall:** I do not optimize for hypothetical scale. I instrument the system, measure the workload, identify the bottleneck, and then choose the appropriate scaling technique.

### Current audit status

Economics / entitlement truth — GREEN
Authentication / authorization — GREEN
AI generation runtime + frontend contract — GREEN
Realtime + E2EE — NOT GREEN; 4 test failures remain
Later gates remain blocked until earlier required gates are proven.

## Latest Realtime/E2EE fixes — 2026-10-05

### What the 70-pass / 4-fail QA run taught us
The four failures reduced to three root causes: duplicate offline study routes, Flask realtime hooks being registered from `realtime_server.py` after the app had already served a request, and the direct E2EE message endpoint accepting a plaintext body without a nonce.

### What we fixed
- Removed the older duplicate `/study-time/offline-baselines` and `/study-time/offline-sync` implementations from `app.py`; the startup-registered `offline_activity_routes.py` implementation is now canonical.
- Removed the three Flask `after_request` realtime hooks from `realtime_server.py`. They were lifecycle-unsafe because importing the realtime entrypoint could happen after Flask had already handled a request.
- Added `chat_realtime_dispatch.py` so message delivery is explicitly dispatched **after the database commit**. Redis-backed deployments enqueue to the durable chat stream; local/single-instance mode lazily uses Socket.IO direct delivery. Dispatch failures are logged without pretending database persistence failed.
- Strengthened the message and edit contract so both `direct_v1` and `group_v1` E2EE messages require a nonce whenever a body is supplied. Plaintext is rejected with HTTP 409 before persistence.
- Moved chat timestamp normalization into `_serialize_chat_message()` instead of another late Flask response hook.

### Why this design is better
The important lifecycle rule is: **construct the Flask application and register all routes/hooks during startup; do not mutate application setup after the first request.** Realtime delivery is a post-commit side effect, not a Flask response-hook dependency. PostgreSQL remains the durable source of truth; Redis/Socket.IO are delivery infrastructure.

### Evidence still required
The code fixes are on `main`, but Gate 4 is not GREEN until the standard local QA suite is rerun and passes, followed by the Redis-backed realtime smoke test and the calling runtime test.

### Interview-ready explanation
> “We found a lifecycle bug where realtime behavior depended on importing a module that registered Flask hooks after requests had already started. I moved delivery to an explicit post-commit dispatch path and kept PostgreSQL as the source of truth. We also found a security-contract gap where direct E2EE messages could carry plaintext; the endpoint now requires an encryption nonce for E2EE bodies and rejects invalid writes before persistence.”



## 2026-10-05 — Realtime/E2EE gate: full QA now GREEN

### Latest evidence

The standard Docker QA loop was rerun from `origin/main` at commit `fb44ed4`:

- Docker image build: **successful**
- PostgreSQL and Redis: **healthy**
- Test dependencies: **installed**
- Alembic upgrade head: **OK**
- Full real-world QA suite: **74 passed, 0 failed, 3375 warnings**
- QA database: retained for inspection

The previous five realtime failures are therefore resolved at the full integration-test level.

### What this proves

This is stronger evidence than the earlier static checks because the suite exercised the application against the real PostgreSQL-backed local environment and reached the realtime/E2EE integration boundaries.

The warning count does **not** represent failed tests. The warnings are mainly technical-debt items such as deprecated `datetime.utcnow()` usage and a legacy SQLAlchemy `Query.get()` call. They should be cleaned up later, but they do not currently block correctness.

### Important architecture lesson

Prepza has two different responsibilities in the realtime path:

**Durable truth**
- PostgreSQL stores the persisted message state.
- The HTTP message route commits the database transaction first.

**Delivery**
- Socket.IO provides low-latency delivery.
- Redis provides the cross-process/multi-instance message queue and chat event stream when configured.
- The dedicated chat worker consumes the Redis Stream and republishes through Socket.IO.

This distinction matters because receiving a realtime event is not the same thing as proving that the message is durably stored.

### Why we are doing two more explicit checks

The 74/74 suite is enough to move the integration suite from failing to passing, but local QA currently configures `REDIS_URL=memory://` for its realtime tests. That exercises the direct/single-instance Socket.IO path.

Before declaring the production-style realtime gate completely GREEN, we therefore need explicit evidence that:

1. the actual Redis-backed path connects and is enabled;
2. the dedicated chat worker can consume Redis events;
3. authenticated call signaling works through `scripts/test_calling_runtime.py`.

### Commands to run next

From `~/prepza` in Git Bash:

    docker compose -f docker-compose.vps.yml up -d

    docker compose -f docker-compose.vps.yml ps

    docker compose -f docker-compose.vps.yml exec app python -c "from realtime_server import REALTIME_REDIS_ENABLED, REALTIME_REDIS_URL, _realtime_redis; print('REALTIME_REDIS_ENABLED=', REALTIME_REDIS_ENABLED); print('REALTIME_REDIS_URL=', REALTIME_REDIS_URL); print('REDIS_PING=', _realtime_redis.ping() if _realtime_redis else None)"

    docker compose -f docker-compose.vps.yml exec app python scripts/test_realtime_runtime.py

    docker compose -f docker-compose.vps.yml exec app python scripts/test_calling_runtime.py

    docker compose -f docker-compose.vps.yml logs --tail=100 chat-worker

The first command proves the production-style Compose stack is running. The Redis Python check proves the application is actually configured to use the Compose Redis service rather than silently falling back.

The realtime script and calling script prove the authenticated Socket.IO/calling behavior. The worker logs let us verify that the dedicated Redis chat worker starts cleanly.

### Learning today

I learned an important distinction:

> A system can pass its integration tests while still needing a separate test of a production-only infrastructure path.

That is not a contradiction. It means we deliberately test both the common application behavior and the infrastructure mode that will exist in production.

I also learned to think of Redis as **delivery infrastructure**, not as the permanent database for chat messages.

### Interview-ready explanation

> “I separated persistence from delivery. PostgreSQL is the source of truth for chat state; Socket.IO handles low-latency delivery; Redis provides cross-process fan-out and the event stream; and a dedicated worker consumes queued events. I don't treat successful realtime delivery as proof of durable persistence, so I test those concerns separately.”

### Audit status after 74/74

- Economics / entitlement truth — GREEN
- Authentication / authorization — GREEN
- AI generation runtime + frontend contract — GREEN
- Realtime/E2EE integration suite — GREEN
- Realtime production-style Redis path — **verification pending**
- Calling runtime — **verification pending**
- Storage/data integrity — BLOCKED until the required realtime verification is complete


## 2026-10-05 — Calling runtime reconciliation

### What we discovered
The calling feature was supposed to exist end-to-end. The current frontend still contained the WebRTC call experience and call signaling client, and the repository still contained the calling runtime regression test and architecture audit. However, `realtime_server.py` on current `main` had lost the backend WebRTC signaling handlers and `_active_calls` state. This caused `scripts/test_calling_runtime.py` to fail during collection with `cannot import name '_active_calls'`.

This was a real implementation/source-of-truth drift issue, not a Docker or Python import problem. Historical repository tooling confirmed that `tools/apply_calling.py` is the intended backend/frontend wiring patch.

### What changed
Restored the authenticated calling signaling boundary directly on `main`:
- `_active_calls` state and lock
- authenticated caller/target validation
- exact two-member conversation membership check
- voice/video invite routing
- accept/reject/end lifecycle
- WebRTC offer/answer/ICE routing
- target-only delivery through Socket.IO

The media itself still stays peer-to-peer through WebRTC; the server carries signaling metadata only.

### Why this matters
A frontend can still contain a complete feature while the backend contract it depends on is missing. Static/frontend checks therefore cannot prove the feature works. The runtime calling test is valuable because it exercises the actual Socket.IO handlers and authorization boundary.

### Interview-ready explanation
> "During the production-readiness audit I found a source-of-truth drift bug: the frontend and regression tests still expected WebRTC calling, but the realtime server no longer registered the corresponding signaling handlers. Instead of weakening the test, I traced the repository history to the intended calling patch, restored the authenticated signaling boundary, and then verified it through runtime tests."

### Verification still required
Rebuild and force-recreate the realtime/app containers from current `main`, reinstall test requirements, then run both `scripts/test_calling_runtime.py` and `scripts/test_realtime_runtime.py`. Do not mark the realtime/calling gate green until those runtime results are pasted and passing.


## 2026-10-05 — QA documentation and Python one-liner lesson

### What we documented

Added **actualtest.md** as the exact human-readable map of the full local QA suite.

Current verified structure:
- 10 QA test files
- 71 `test_...` functions
- 74 collected pytest cases
- 7 controlled QA users: 6 students + 1 admin
- 2 disposable organisation tenants used by authorization tests
- latest full run: **74 passed, 0 failed, 3375 warnings**

actualtest.md lists every test function, what it verifies, the controlled user roles, the suite boundaries, and what the 74/74 result does and does not prove.

### New Python lesson

The command we first tried failed with a `SyntaxError` because `python -c` executes a single simple statement and does not accept a compound `with ...:` block after a semicolon.

The important idea is not a Docker problem. Flask-SQLAlchemy requires an **application context** before using `db.session`.

A compact valid pattern for this kind of diagnostic is:

    docker compose -f docker-compose.vps.yml exec app python -c "from app import app, db, User; ctx=app.app_context(); ctx.push(); users=[db.session.get(User,i) for i in (7,8,9)]; [print('user_id=',u.id,'session_version=',u.session_version,'suspended=',u.is_suspended) for u in users if u]; ctx.pop()"

### Why this matters

This taught me to distinguish:

- **Python syntax/context errors** — the diagnostic command itself is invalid or lacks the Flask application context;
- **database/application errors** — the command runs but the data or application behavior is wrong.

The failed command therefore gave us no evidence yet about users 7, 8, and 9. We need a valid application-context query before changing the realtime tests.

### Interview-ready explanation

> "When debugging Flask-SQLAlchemy from a container shell, I have to establish the Flask application context before accessing `db.session`. I also learned that Python's `-c` mode does not allow a compound `with` block after a semicolon, so for compact diagnostics I can explicitly push and pop an application context."

### Realtime test-user lesson

The focused runtime scripts use persistent local database identities differently from the disposable full QA world. The full QA suite creates deterministic users dynamically; the focused scripts currently use hard-coded runtime IDs. Because socket authentication compares the session's `_session_version` with the database's current `User.session_version`, hard-coded session versions can become stale. We must inspect the actual users before weakening or changing the authentication code.


## 2026-10-05 — Focused realtime/calling fixtures made self-contained

### What we discovered

The Docker application database reported:

    USER_COUNT= 0

The focused runtime scripts were still assuming persistent users with IDs 7, 8, and 9. That made their socket sessions fail authentication because the realtime server correctly checks that the session user exists, is not suspended, and has the matching current session version.

The full 74/74 QA suite was not affected because its disposable `prepza_qa` database creates its own controlled users.

### What changed

Added `scripts/runtime_test_fixtures.py`, which creates three isolated runtime users with unique `@test.invalid` emails at test start and removes them afterward.

Updated:
- `scripts/test_realtime_runtime.py`
- `scripts/test_calling_runtime.py`

Both now:
- use dynamically created database user IDs;
- use the users' real `session_version`;
- avoid assumptions about IDs 7/8/9;
- clean up their temporary users;
- continue exercising the real authenticated Socket.IO boundary;
- keep the membership/calling authorization checks mocked only where the test is specifically isolating realtime behavior.

The realtime message test was also reconciled with the current architecture: it now calls `dispatch_message()` rather than the removed `broadcast_message_response()` helper.

### Why this matters

A runtime test should own the test data it depends on. Database primary keys are implementation details, not stable identities.

This is also a security lesson: when a test failed because its users did not exist, the correct response was **not** to bypass authentication. The authentication failure was correct. We fixed the fixture instead.

### Interview-ready explanation

> "I found that a focused Socket.IO regression test depended on hard-coded database IDs and a hard-coded session version. In a fresh environment the database had zero users, so authentication correctly rejected the sockets. I made the runtime test self-contained by creating disposable users, reading their real IDs and session versions, and cleaning them up afterward. That keeps the test realistic without weakening the authentication boundary."

### Verification required next

Fetch current `main`, rebuild and force-recreate the app/realtime/chat-worker containers, reinstall test requirements, then run the focused realtime and calling tests.

The expected first verification mode is `REDIS_URL=memory://` because Flask-SocketIO's in-process test client cannot be initialized with the production Redis message queue configured. After the Socket.IO behavior passes, separately verify the production Redis path with the real `redis://redis:6379/0` configuration and the chat worker.

### Audit status

- Economics / entitlement truth — GREEN
- Authentication / authorization — GREEN
- AI generation runtime + frontend contract — GREEN
- Realtime/E2EE integration suite — GREEN
- Focused realtime Socket.IO runtime — **verification pending after fixture fix**
- Production-style Redis path — **verification pending**
- Calling runtime — **verification pending after fixture fix**
- Storage/data integrity — BLOCKED until required realtime/calling verification is complete


## 2026-10-05 — Authoritative QA inventory and release-gate discipline

### What we did

We stopped treating the QA work as a collection of commands that I have to remember manually. We inventoried the existing tests and separated them into:

- the **74-case full local integration suite**;
- the focused **authenticated realtime runtime** test;
- the focused **authenticated calling runtime** test;
- the future **Redis-backed production-style** verification;
- later external-provider and deployed-environment gates.

The full suite already contains 10 test files and 71 test functions, producing 74 collected cases because the generation-ceiling test is parametrized across four material types.

### Current evidence

- Full local QA: **74 passed, 0 failed, 3375 warnings**.
- Calling runtime: **4 passed in 3.31s** after replacing fixed/hard-coded runtime identities with disposable database-backed fixtures and preserving real authentication.
- Focused realtime runtime: the command has been part of the verification sequence, but the exact latest numeric result is not preserved in the current notes. We will not invent one. This is an evidence-quality lesson in itself.
- Redis-backed runtime path: still a distinct gate because the full local suite intentionally sets `REDIS_URL=memory://`.

### Why we are not simply adding more tests

The repository already has substantial coverage. The problem is not “more test files” by itself.

The real goal is:

**student action -> frontend -> HTTP/Socket.IO -> Flask -> service logic -> PostgreSQL/storage -> background worker -> response/realtime event**

A master QA command should therefore orchestrate existing tests and add only the missing true end-to-end behavior. Duplicating the same assertions in another file would make maintenance harder without increasing confidence.

### New QA rule I learned

A test can be:

- implemented;
- executed;
- passed;
- production-proven.

Those are four different claims.

For example, the 74/74 suite proves strong local integration behavior, but it deliberately uses an in-process Redis mode for its realtime tests. That does not prove the separate multi-process Redis/chat-worker deployment path.

### The release gate we are building

The eventual single command will report these gates:

1. Environment/database
2. Authentication/session
3. Authorization/ownership
4. Economics
5. AI runtime
6. Realtime/E2EE
7. Calling
8. Storage/data integrity
9. PWA/offline
10. Failure/concurrency

Each gate should reuse the repository's existing focused tests. The overall result is GREEN only when every required gate has passing evidence.

### Important economics lesson

The economics gate is not merely “the plan constants are correct.”

It must trace the student's actual entitlement lifecycle:

**plan selected -> payment/provider result -> fulfillment/activation -> allowance granted -> AI request -> exact usage charged -> remaining allowance -> hard stop at limit -> expiry/future-start boundary**

That is the level of evidence needed for the question: “Does a paying student actually receive exactly what they paid for, and does it end exactly when the contract says it ends?”

### Important runtime lesson

The focused calling test exposed a real source-of-truth problem: frontend calling behavior and test expectations can survive while backend signaling handlers disappear. The correct response was to restore the real authenticated backend contract, not to weaken the test.

The focused runtime fixtures also taught another lesson: tests should create the database identities they depend on. Hard-coded user IDs and session versions are not stable test fixtures.

### Next step

The next implementation step is to create the single master local runtime QA orchestrator around this inventory. It should:

- run the existing suites in a known order;
- print a named result for each gate;
- stop or continue according to dependency rules;
- preserve exact command/results;
- distinguish skipped, failed, and passed gates;
- avoid duplicating business assertions.

Only after that local gate is stable should we treat external-provider QA and deployed launch smoke as the next layers.


## 2026-10-05 — Focused realtime runtime verification completed

### What we did

We rebuilt the current `main` Docker application from scratch, force-recreated the application container, installed the test requirements, and reran the previously unpreserved focused realtime runtime gate.

The exact command was:

    docker compose -f docker-compose.vps.yml exec -e REDIS_URL=memory:// app python -m pytest scripts/test_realtime_runtime.py -q

### Result

    .........                                      [100%]
    9 passed in 2.98s

### What this proves

The focused authenticated Socket.IO runtime gate is now **GREEN**.

The 9 cases verify:

- unauthenticated socket rejection;
- conversation membership enforcement;
- member join/presence;
- repeated join protection;
- disconnect presence;
- multi-tab presence;
- explicit leave behavior;
- authenticated typing/read/message dispatch;
- non-member leave authorization.

The tests use disposable real database users and their current session versions, so the authentication boundary remains real.

### Important boundary

This run uses:

    REDIS_URL=memory://

That is intentional for the in-process Flask-SocketIO test client. It proves the focused authenticated realtime behavior, but it does **not** prove the production-style multi-process Redis/chat-worker path.

### Current release-gate evidence

- Full local integration suite: **74 passed, 0 failed, 3375 warnings — GREEN**
- Focused realtime runtime: **9 passed in 2.98s — GREEN**
- Focused calling runtime: **4 passed in 3.31s — GREEN**
- Redis-backed production-style realtime path: **NEXT / NOT YET PROVEN**

### Next step

The next local test should verify the real Docker Redis path and dedicated chat worker without duplicating the already-green Socket.IO assertions.

The question is now:

**Can a realtime event/message traverse the actual Redis-backed multi-process architecture, with PostgreSQL remaining the durable source of truth and the dedicated chat worker consuming/recovering Redis Stream work correctly?**

No paid infrastructure, VPS migration, GPU purchase, or production deployment is part of this gate.


## 2026-10-05 — Prepared the real Redis chat-worker gate

### What we changed

We moved to the next realtime question: **does the actual Redis-backed background worker path work, rather than only the in-process Socket.IO test path?**

I added:

    scripts/test_redis_chat_worker_runtime.py

The script starts the real chat_event_worker.py process with isolated Redis Stream/group names, puts a controlled chat event into the real Redis Stream, and waits for two pieces of evidence:

- the worker acknowledges the Redis Stream entry;
- the worker publishes the corresponding chat:message event onto the prepza-realtime Socket.IO Redis channel for the correct room.

### Why this matters

The previous focused realtime result was:

**9 passed in 2.98s**

but it deliberately used:

    REDIS_URL=memory://

That proved authenticated Socket.IO behavior and realtime authorization, but it did not prove the production-style Redis Stream/worker path.

The new test targets that missing boundary.

### What I learned

A realtime architecture can have several separate hops:

    PostgreSQL persistence
        ↓
    Redis Stream
        ↓
    chat-worker
        ↓
    Socket.IO Redis message queue
        ↓
    realtime server
        ↓
    connected browser

A test must say exactly which hops it proves. We should not call the entire chain green just because one in-process Socket.IO test passes.

### Current status

**Redis-backed worker gate: PREPARED / NOT YET EXECUTED.**

After refreshing local main, run the standard rebuild/install loop and then:

    docker compose -f docker-compose.vps.yml exec app python scripts/test_redis_chat_worker_runtime.py

The final browser-facing multi-process delivery check will come after this worker/Redis gate.

### Interview-ready explanation

> I separated the realtime tests by boundary. The first suite verifies authenticated Socket.IO behavior in-process. The next runtime test starts the real Redis-backed chat worker, injects an event into a Redis Stream, verifies acknowledgement, and verifies publication onto the Socket.IO Redis channel. This lets me prove each distributed-system hop instead of claiming the whole architecture works from a single test.


## 2026-10-05 — Real Redis chat-worker runtime gate passed

### Exact command

    docker compose -f docker-compose.vps.yml exec app python scripts/test_redis_chat_worker_runtime.py

### Exact result

    PASS: real Redis chat worker consumed and acknowledged the event
    PASS: worker published chat:message onto prepza-realtime for the conversation room
    PASS: Redis stream entry 1791203715146-0 was processed

### What this proves

The dedicated Redis-backed chat-worker path is now **GREEN**.

We proved the actual Docker Redis service was reachable, the real `chat_event_worker.py` consumed a controlled Redis Stream event, acknowledged it, and published the corresponding `chat:message` event onto the `prepza-realtime` Socket.IO Redis channel for the correct conversation room.

This is stronger than the earlier `REDIS_URL=memory://` focused Socket.IO tests because it exercises the real background worker and Redis infrastructure.

### What remains

We still need to prove the final client-facing distributed hop:

    Redis publication
        ↓
    separate realtime container
        ↓
    connected Socket.IO client

Do not call the complete multi-process realtime path green until that test passes.

### Next test

A dedicated script was added:

    scripts/test_redis_realtime_client_runtime.py

Run it with:

    docker compose -f docker-compose.vps.yml exec app python scripts/test_redis_realtime_client_runtime.py

It creates disposable authenticated users and a real database-backed conversation, connects a real Socket.IO client to the separate `realtime` service, starts the real chat worker with an isolated Redis Stream/group, injects one controlled event, and verifies the client receives `chat:message`.

This is deliberately a new boundary test, not a duplicate of the already-green 9-case authenticated Socket.IO suite.


### 2026-10-05 — Cross-process client test harness correction

The first run of:

    docker compose -f docker-compose.vps.yml exec app python scripts/test_redis_realtime_client_runtime.py

did not reach Redis, Socket.IO, authentication, or the realtime process. It stopped immediately with:

    ModuleNotFoundError: No module named 'app'

Root cause: Python's script import path was `/app/scripts`, but `app.py` lives at `/app/app.py`.

This was a test harness defect. The script has been corrected to insert the repository root into `sys.path` before importing Prepza modules.

Status remains **NOT YET PROVEN** for the final Redis → separate realtime process → real Socket.IO client hop. No production or paid infrastructure change was made.


## 2026-10-05 — Cross-process realtime client delivery gate passed

### Exact command

    docker compose -f docker-compose.vps.yml exec app python scripts/test_redis_realtime_client_runtime.py

### Exact result

    PASS: real Socket.IO client connected to the separate realtime process
    PASS: authenticated client joined the real database-backed conversation
    PASS: Redis Stream -> chat-worker -> Redis Socket.IO queue -> realtime process -> client delivered chat:message
    PASS: Redis stream entry 1791205395549-0 was acknowledged

### What this means

We have now proven the missing final local distributed realtime hop. The test used the actual Docker Redis service, the actual `chat_event_worker.py`, the actual separate `realtime` container, and a real authenticated Socket.IO client.

The path tested was:

    Redis Stream
        ↓
    chat-worker
        ↓
    Redis Socket.IO queue
        ↓
    separate realtime process
        ↓
    connected Socket.IO client

The client joined a real PostgreSQL-backed conversation and received the expected `chat:message`. The Redis Stream entry was acknowledged, so the worker did not merely publish and leave the job pending.

### Why this is important

Previously we had three separate pieces of evidence:

- 74/74 full local QA;
- 9/9 focused authenticated realtime tests using `REDIS_URL=memory://`;
- the real Redis chat-worker gate.

Those did not, by themselves, prove the complete multi-process client-facing path.

This test closes that gap for the controlled local Docker scenario.

### Debugging lesson from the failed first attempt

The first cross-process test attempt failed with:

    ModuleNotFoundError: No module named 'app'

The failure happened before any Redis, authentication, Socket.IO, or realtime assertion. Git and the local working tree already contained the import-path correction, but the running Docker image still contained the older script.

We therefore rebuilt the app image with `--no-cache`, recreated the relevant containers, verified the corrected script inside `/app/scripts/`, and reran the test.

The corrected container then passed all four assertions.

### Current release-gate evidence

- Full local integration: **74 passed, 0 failed, 3375 warnings — GREEN**
- Focused realtime: **9 passed in 2.98s — GREEN**
- Focused calling: **4 passed in 3.31s — GREEN**
- Redis-backed chat worker: **GREEN**
- Redis-backed cross-process client delivery: **GREEN**

### What is still not proven

This closes the local Docker distributed realtime gate, but it is not the same as proving a public production deployment. We still need later environment-level evidence for things such as real browser/PWA behavior, external provider integrations, internet/network conditions, load behavior, backups/restore, and the actual deployed environment.

No paid VPS migration, GPU purchase, or production infrastructure change was made by this test.


## 2026-10-05 — Real browser-to-browser WebRTC gate prepared

### What we are testing next

The backend calling signaling gate is green, but I do not want to call calls fully end-to-end until two actual browser instances exchange real WebRTC media.

The new test is:

    scripts/test_browser_webrtc_runtime.py

It uses two independent Chromium contexts with fake microphone/camera devices, real Prepza login sessions, the real calling UI event, the real Socket.IO signaling path, and real browser `RTCPeerConnection` objects created by `CallExperience.tsx`.

### Exact host commands

Install the browser test dependency once:

    python -m pip install playwright
    python -m playwright install chromium

Keep the normal Docker stack running, then from the repo root run:

    python scripts/test_browser_webrtc_runtime.py

### What a green result will mean

A green result will prove, locally:

- two independent real browsers authenticate;
- the caller starts the real calling experience;
- the callee receives and accepts the call;
- offer/answer/ICE signaling traverses the real Socket.IO backend;
- both browsers reach the application's **Connected** state;
- both browsers receive a live remote audio MediaStream track.

That is the missing evidence for the statement **"calling works end-to-end locally."**

### Current status

**PREPARED / NOT YET EXECUTED.**

Do not mark the calling gate green until the script actually passes.

### Next release gate after browser calling

If this browser WebRTC gate passes, the next release gate is **Storage/Data Integrity**, with emphasis on the launch-readiness requirement that the database and uploaded/generated data are actually recoverable.

The repository launch sequence explicitly requires a successful database restore, backup + restore + rollback rehearsal, and proven storage recovery before launch-ready status. The current launch-readiness document also says R2 support exists but legacy Supabase Storage fallback remains, so we should verify the real backup/restore and storage paths rather than assuming the provider abstraction is enough.

The likely local sequence after the browser gate is:

1. PostgreSQL backup creation.
2. Disposable restore into a fresh database.
3. Restore verification against important Prepza tables/relationships.
4. Storage/object recovery verification for the provider-neutral storage layer.
5. Then PWA/offline browser behavior and failure/concurrency evidence where still missing.

No VPS migration or paid infrastructure change is part of this work.


## 2026-10-05 — Browser WebRTC gate hit test-harness defects

The first real browser execution was useful even though it did not reach WebRTC.

It proved:

- the host Playwright/Chromium setup works;
- the script can create real disposable users/conversation data;
- two independent browser contexts can authenticate against the running Prepza app.

It then failed on an incorrect assumption in the test:

    KeyError: 'id'

The cleanup code also failed because login created `user_key` records that must be removed before deleting the disposable users.

I corrected both issues directly on `main` in:

    f3eb880c718f1f564bca83829bb62f3fddbd2786

### Important interpretation

This is not evidence that calls fail. It is not evidence that calls pass either. The script stopped before the actual WebRTC negotiation/media portion.

Current calling gate remains:

- authenticated calling/signaling: **GREEN (4/4)**
- real browser-to-browser media: **NOT YET PROVEN**

### Next action

Refresh local `main` so the corrected browser gate is inside the working checkout, then rerun the browser gate. Do not proceed to Storage/Data Integrity until this gate either passes or exposes a real application defect that needs fixing.
