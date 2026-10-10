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

### Historical audit snapshot

At the time these notes were written, the realtime/E2EE gate still had four failures. That snapshot was subsequently resolved and must not be read as the current release status. The later 74/74 QA record is authoritative for the current full-suite result.

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

### Historical status

**PREPARED / NOT YET EXECUTED** at the time of this entry. Later entries document the subsequent browser-gate attempts; the current browser-to-browser media gate remains **NOT YET PROVEN**.

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

## 2026-10-05 — Browser WebRTC harness corrected: local session and cleanup

The browser calling gate reached the real browser layer but was blocked by test setup rather than by WebRTC itself.

The important discovery was the Flask session-cookie configuration:

    SESSION_COOKIE_SECURE = True

The browser test was using `http://127.0.0.1:5000`. For this local browser test, the safer origin is `http://localhost:5000`, where Chromium treats Secure cookies as usable on the localhost development origin.

The test also had a Python f-string mistake in its cleanup SQL. The SQL parameter dictionary needed escaped braces because the surrounding Docker fixture code is itself an f-string.

### What we changed

- Default browser test URL: `http://localhost:5000`.
- Login helper now verifies the resulting authenticated session through `/me`.
- The callee ID used for signaling comes directly from that verified authenticated session.
- Cleanup dictionary braces are escaped correctly.
- `playwright>=1.55,<2` is now declared in `requirements-test.txt`.
- Chromium remains a separate browser installation, not a production dependency.

### Why this is a good test design

The test should not print "authenticated" merely because `POST /login` returned success. It should prove that the browser can subsequently use the session for an authenticated request.

Interview-ready explanation:

> "The first browser test was too optimistic because it treated a successful login response as proof that the browser session was usable. I changed it to verify the authenticated session with the real `/me` endpoint before starting the call. I also fixed the disposable-fixture cleanup path and made the browser dependency explicit in the test requirements."

### Current status

**Browser WebRTC media: NOT YET PROVEN.**

The next execution is the same browser gate, now with the corrected local-origin/session handling.


## 2026-10-05 — Browser WebRTC gate: session harness passed, call UI handoff now blocked

The corrected browser gate was executed after refreshing `main` and installing the declared test dependencies.

### Dependency installation clarification

The requirements were intentionally installed in **two different environments**:

1. `docker compose ... exec app python -m pip install -r requirements-test.txt`
   - installs the Python test dependencies **inside the Docker app container**;
   - this keeps container-side pytest/runtime scripts reproducible.

2. `python -m pip install -r requirements-test.txt`
   - installs the same test dependencies in the **Windows host Python environment**;
   - this is required because `scripts/test_browser_webrtc_runtime.py` is deliberately a host-side Playwright test that launches Chromium on Windows and connects to the Dockerized application.

3. `python -m playwright install chromium`
   - installs the actual Chromium browser binary for the host-side Playwright package;
   - pip installs the Python Playwright library, but does not install the browser binary itself.

Installing the requirements twice was therefore **not duplicate work in the same environment**. It synchronized both environments needed by this particular test.

### Why the corrected test got further this time

The previous run failed at `/me` with HTTP 401. The corrected test changed its default browser origin from `http://127.0.0.1:5000` to `http://localhost:5000` and verifies the authenticated session immediately after login.

This run reached:

    PASS: disposable browser-call users and conversation created
    PASS: two independent real browser contexts authenticated

That means the previous session/authentication harness problem is resolved. The test now reaches the actual call UI stage.

### New result

The test then failed waiting 10 seconds for:

    get_by_role("button", name="Accept call")

Current result:

**Browser WebRTC media: NOT YET PROVEN.**

This is not yet evidence that WebRTC media is broken. The test has reached the call-incoming UI boundary, but the expected accessible button was not visible. The next investigation is to inspect the actual incoming-call UI/event flow and make the browser test target the real current UI contract rather than assuming the button text/role.

The previous `/me` failure is therefore GREEN/corrected; this is now a new browser-call test/UI contract investigation.


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


## 2026-10-05 — Browser WebRTC gate: fixture error-formatting defect

The latest browser WebRTC run did not reach Chromium, login, calling, or WebRTC. It stopped while creating the disposable database fixture with:

    NameError: name 'university' is not defined

This was another **test-harness defect**. The browser fixture is generated inside an outer Python f-string. The inner generated fixture contained an f-string error message using `{university.id}`. The outer f-string evaluated that expression immediately, before the generated fixture had executed its university lookup.

So the important distinction is:

- the real onboarding fix from the previous run remains valid;
- the active-university/active-program lookup was not actually reached in this run because fixture source generation failed first;
- this run provides no evidence for or against WebRTC, calling signaling, or browser media.

The correction was committed directly on `main` as:

    2a256a54628fa01a3059fc3ab385affd2e80c95c

The error message now uses string concatenation instead of an inner f-string expression, so the generated fixture can execute the database lookup normally.

### Current status

**Browser WebRTC media: NOT YET PROVEN.**

The next execution should be the same browser gate after refreshing to this commit. We should not move to the storage/data-integrity release gate until this browser call path either passes or exposes a genuine application defect.


## 2026-10-05 — Browser WebRTC gate: local reference-data prerequisite missing

The corrected browser WebRTC fixture reached its real database prerequisite check and failed with:

    RuntimeError: Container fixture command failed:
    RuntimeError: No active university exists for browser WebRTC fixture

This means the previous outer-f-string defect is fixed and the fixture is now executing normally. The test has still not reached Chromium or WebRTC media.

Repository inspection found `seed_universities_and_programs.py` on main and it is specifically designed to seed the university/program catalog. It is idempotent: existing universities are matched by exact name and existing programs by `(university_id, name)`, so rerunning it does not intentionally duplicate the catalog.

The correct next action is to initialize the local QA database using that existing seed script, rather than modifying the browser test to invent fake reference data. After seeding, rerun the browser WebRTC gate unchanged.

### Current release-gate status

**Browser-to-browser WebRTC media: NOT YET PROVEN.**

The failure is classified as **LOCAL TEST-ENVIRONMENT PREREQUISITE**, not an application defect. Do not advance to the storage/data-integrity release gate until the browser call/media path passes or exposes a genuine application failure.


## 2026-10-05 — Browser WebRTC gate: reference data fixed; call UI mount + cleanup defects exposed

The local database was correctly initialized using `seed_universities_and_programs.py`: 103 active universities and 15,038 active programs now exist. This confirms the earlier reference-data blocker was only local test-environment initialization.

The next browser run proved both disposable users could authenticate in independent Chromium contexts. It then timed out waiting for the callee's Accept button. The debug page was the authenticated Home screen, which led to a repository-level finding: `CallExperience` is mounted inside `WhatsAppChatExperience`, not globally on the Home shell. Therefore the browser fixture was authenticating correctly but was not opening the conversation route that mounts the incoming-call UI.

The cleanup phase also found a real test-harness dependency: first-run browser use creates `study_streak`, so the disposable users cannot be deleted until those dependent rows are removed. That is a fixture cleanup issue, not a production FK defect.

I fixed the browser gate on main to open the real conversation route in both contexts and to delete `study_streak` rows before deleting the disposable users.

Commit: `32d58d6612731e8129546d49c302887b20c7b71a`.

**Current release-gate status: Browser-to-browser WebRTC media NOT YET PROVEN.** The next run is the first clean attempt after these two harness corrections.


## 2026-10-05 — Chat/calling UX audit: findings and first redesign pass

I audited the actual active chat/calling code before changing the WebRTC test. The key finding is that the calling UI was not designed as a global app-level communication layer. CallExperience lived inside WhatsAppChatExperience, and a second copy existed in the legacy chat-detail component. That makes incoming-call behavior depend on which screen is mounted and risks duplicate Socket.IO listeners.

The desired Prepza contract is now explicit:

1. A logged-in student has one global CallExperience mounted by the main app shell.
2. A caller can start a call from the real chat UI.
3. A callee can be on Home or another Prepza screen and still receive the incoming-call surface.
4. Offline/unreachable recipients must not leave the caller stuck on Calling… forever.
5. Outgoing calls have a bounded no-answer window; incoming calls also expire if ignored.
6. Functional UI controls use custom SVG icons and accessible labels, never Unicode emoji/symbols as the actual button graphics.
7. User-entered emoji reactions are still allowed because they are message content, not application controls.
8. The browser gate must exercise the real UI button rather than dispatching a synthetic start-call event when a real button is available.

The first implementation pass moved CallExperience to the app shell, removed the duplicate chat-mounted instance, added bounded Socket.IO acknowledgements, added recipient-delivery detection, added no-answer/unavailable handling, and replaced call-control Unicode glyphs with custom SVG controls.

The backend currently rejects call invites unless the conversation contains exactly two active participants. Therefore I am not pretending group calling is implemented yet. The next design phase should specify participant selection, add-person behavior, group call state, call history, and the server-side call state model before implementing group calls.

Current status: redesign committed to main; local build/browser verification still pending.


## 2026-10-05 — Build failure from source-transformer drift

The first local rebuild after the global calling redesign exposed an important repository pattern: the frontend build runs many source transformation scripts before Vite. `apply_call_history.py` still searched for the old one-line `call:incoming` handler and therefore stopped the build with `CALL_HISTORY_FAILED: incoming handler missing`.

This was not a Docker, pnpm, or dependency failure. `pnpm install --frozen-lockfile` completed successfully; the failure occurred inside the project's own prebuild transformation chain. The transformer has now been updated to recognize the redesigned incoming-call handler and to skip duplicate history insertion on subsequent runs. This is exactly the kind of source-of-truth reconciliation the local production-style build is intended to catch.

Do not treat the containers started after the failed build as proof of the new frontend. Rebuild the app image after refreshing `main`, then run the frontend build and browser gate again.

## 2026-10-05 — Lesson: the source-transformer build gate is now green

### What happened

After the previous calling redesign, the Docker build had failed inside the frontend prebuild chain with:

    CALL_HISTORY_FAILED: accept handler missing

We refreshed the checkout to origin/main and rebuilt the app image. The current commit is **c09c7eb** (fix global call realtime listener dependency). The complete Docker build finished successfully: **22/22 steps**, including the frontend command:

    pnpm install --frozen-lockfile && pnpm run build

The final image was exported as prepza-app:latest.

### Why it mattered

The failure was caused by drift between a source transformation script and the redesigned CallExperience.tsx. That meant the code could look valid while the actual production-style build could still fail. The successful rebuild proves that this source-transformer mismatch is no longer blocking the image build.

### What I learned

A build pipeline can contain more than the compiler/bundler. Prepza's frontend build also runs repository-specific transformation scripts. Those scripts are part of the real source-to-runtime contract and must remain compatible with source-code refactors.

A simple mental model is:

    source code -> prebuild transformations -> Vite build -> Docker runtime image

If any stage breaks, the application is not deployable even when the TypeScript itself looks reasonable.

### Evidence

- git reset --hard origin/main reached c09c7eb.
- Docker reported [+] build 1/1 and Image prepza-app Built.
- The frontend build step completed rather than stopping at CALL_HISTORY_FAILED.
- Runtime image creation and export completed successfully.

### Interview-ready explanation

> After redesigning the calling UI, the Docker build exposed a source-transformer compatibility problem. I traced the failure to the prebuild transformation layer rather than Docker or pnpm. After reconciling the transformer with the new source structure, I rebuilt from the exact main commit and verified the full 22-step image build succeeded. I still treat runtime and browser tests separately because a build proves packaging, not behavior.

### Next step

Recreate the app/realtime/chat-worker services from the newly built image, then run the full local QA and the real browser WebRTC gate. The browser calling gate remains **NOT YET PROVEN** until it actually establishes browser-to-browser media.


## 2026-10-05 — Lesson: a green full QA suite means the rebuilt runtime still matches the application contracts

### What happened

After recreating the production-style Docker services from the newly successful app image, I ran the complete local QA runner. The disposable QA database was migrated with Alembic and the full suite finished with **74 passed, 0 failed in 54.89 seconds**.

### Why it matters

This is stronger evidence than simply seeing containers in a `Started` state. Container startup proves processes launched; the 74/74 suite proves the running application still satisfies a large set of real HTTP, database, authorization, economics, AI, E2EE, and realtime contracts after the rebuild.

### Important economics lesson

The suite includes `test_student_economics_entitlement_lifecycle_and_quota_truth`. That means the current green result is meaningful for the requirement that Prepza's Free/Plus/Pro entitlement lifecycle and remaining AI quota are enforced according to the tested contract, including expiry/future-start boundaries and per-request ceilings. It does **not** mean live Paystack fulfillment, live OpenAI billing, or every production provider integration has been proven.

### Warning interpretation

The **3375 warnings are not failed tests**. Most are deprecation warnings for `datetime.utcnow()`; there is also legacy SQLAlchemy `Query.get()` usage. These should become technical-debt cleanup work, but they are not a reason to mark this QA run red.

### Interview-ready explanation

> After rebuilding and recreating the production-style services, I ran the full local integration suite against a disposable PostgreSQL QA database. Alembic upgraded the database successfully and all 74 collected cases passed. That gives me evidence that the rebuilt runtime still satisfies the application's route, authorization, economics, AI, E2EE, and realtime contracts. I keep the browser WebRTC and external-provider gates separate because passing integration tests does not prove real browser media or live third-party services.

### Current status

The full local QA gate is **GREEN**. The next unresolved release gate remains the real browser-to-browser WebRTC test; after that, continue with storage/data-integrity and controlled external-provider verification.


## Browser WebRTC gate — first host run (2026-10-05)
- The first real-host run reached three green setup checkpoints: fixture creation, independent browser authentication, and caller conversation navigation with callee remaining on Home.
- It then failed while waiting for the caller's real `Start voice call` control (30s Playwright timeout).
- This is currently classified as a **test/render synchronization failure**, not as proof that WebRTC signaling or media is broken. The call button is rendered conditionally after the conversation detail and peer identity are loaded, while the test previously used only a fixed 1.2s delay.
- `scripts/test_browser_webrtc_runtime.py` was hardened on `main` to wait explicitly for that control for up to 15s and emit diagnostic caller UI text/buttons if it remains absent.
- Commit: `aa67d88d326e4518606197d4569ffd0cf8ec427b`.
- Next step is to rerun the browser gate; do not classify the WebRTC path green until the real call reaches Connected and both browsers expose live remote audio tracks.


## Browser WebRTC gate — chat-list visibility failure and fix (2026-10-06)
The browser gate reached a useful boundary before failing: the disposable conversation existed in PostgreSQL and `GET /chats` returned it with HTTP 200, so authentication, session cookies, conversation creation, and server-side chat visibility were functioning. The failure was in the frontend shell: `WhatsAppChatExperience` was mounted for the Chats screen but started with `visible=false`; its own list request was marked internal, so the observer that could set visibility never saw that request. The API row also exposed a null direct-chat name, which the UI did not handle safely. This is a frontend state/data-shaping bug, not evidence of a WebRTC or realtime transport failure.

Commit `a9300823f592f205ce91f773c7ed82273108ba9f` fixes the boundary by making the mounted Chats experience visible immediately, resolving unnamed direct-chat rows from authoritative conversation participants, and making chat-name filtering/rendering null-safe. The browser WebRTC gate must be rerun before calling calling UX/browser media readiness green.


### 2026-10-06 — Browser WebRTC gate build regression and source fix
The browser gate exposed a second-layer source/build issue after the earlier chat visibility diagnosis. The `/chats` API was still healthy, but the Docker frontend build failed before the browser test could use the rebuilt image. TypeScript reported `visible` and `setVisible` as undefined in `WhatsAppChatExperience.tsx`, plus `last_message` missing from `ChatSummary`. Inspection showed the visibility-state explanatory comment contained literal `\\n` text, swallowing the state declaration as part of the comment. The summary type also needed the optional `last_message` property because the hydration/render path reads and writes it. Fixed directly on `main` in commit `18aff73`. Next gate: sync `main`, rebuild the app image, confirm TypeScript/Vite build passes, then rerun `scripts/test_browser_webrtc_runtime.py` to continue toward the actual two-browser media test.


### 2026-10-06 — Lesson: inspect the actual checked-out source when a supposedly fixed build error persists

The first attempted fix for the chat visibility declaration appeared to be committed as `bd3e5fb`, but the local source inspection showed that the file still contained a literal `\n` inside the explanatory comment:

    // legacy direct-navigation detection and must not be the visibility gate.\n  const [visible, setVisible] = useState(true)

Because the declaration was swallowed by the comment, TypeScript correctly reported both `visible` and `setVisible` as undefined.

The important debugging lesson was to stop making assumptions from the commit message and inspect the exact source that Docker was compiling. `grep`, `sed`, and `git diff` exposed the remaining literal characters immediately.

The correction was then made directly in `frontend/src/crypto/WhatsAppChatExperience.tsx`, replacing the literal `\n` with a real newline. `git diff --check` returned clean, and the subsequent Docker build completed all **22/22 steps successfully**.

### Why this matters

The production-style Docker build is testing the actual source-to-image path:

    checked-out source
        -> frontend prebuild transformations
        -> TypeScript
        -> Vite
        -> frontend/dist
        -> Python runtime image

A green commit message is not evidence that every byte of the checked-out source is correct. The compiler and Docker build remain authoritative boundaries.

### Current lesson

The chat visibility source issue is now resolved at the compiler/build boundary.

The next debugging boundary is different: the browser harness previously reached authentication but received HTTP 429 from `/me`. That should be investigated as a rate-limiter/test-isolation problem before rerunning the browser WebRTC gate. It should not be incorrectly classified as a WebRTC failure.

### Evidence

- `git status --short`: only the intended `WhatsAppChatExperience.tsx` source correction was modified.
- `git diff --check`: no errors.
- Docker build: **22/22 steps completed**.
- `prepza-app:latest`: successfully exported.
- TypeScript no longer reports the `visible`/`setVisible` errors.

### Interview-ready explanation

> The browser test exposed a frontend build regression. Instead of assuming the previous fix had worked, I inspected the exact checked-out source and found that a literal `\\n` had swallowed the React state declaration inside a comment. I corrected the source, verified the diff was clean, and rebuilt the production-style Docker image. The full 22-step build then passed. I now separate that build boundary from the remaining browser rate-limit and WebRTC media gates.


## 2026-10-06 — Study Hub study-time design decision

The Study Hub study-time architecture is now captured in `designstudytime.md` before implementation changes are made.

The key decision is to treat **Study Hub as one learning activity system**, not as a collection of independent document timers.

A student can move from Document A to Document B to a quiz and back to Document A while the same Study Hub learning clock continues. The current document, page, and feature are context. They can be retained for analytics, but they must not become separate authoritative clocks that can accidentally double-count time.

This is especially important because the repository already has a local Study Activity accumulator. The correct engineering move is to reconcile that existing mechanism with the backend rather than inventing another timer.

The target data flow is:

```
Study Hub UI
    -> one global activity tracker
    -> browser-persistent accumulated time
    -> low-frequency / lifecycle-triggered sync
    -> Flask validation + idempotency + Nairobi date + daily ceiling
    -> PostgreSQL aggregate
```

Redis remains infrastructure only and is not the source of truth for study time.

### Why batching is useful

The main benefit of accumulating locally for up to roughly an hour is reducing request and transaction frequency, not dramatically reducing database disk usage. PostgreSQL already aggregates StudyTimeLog data instead of storing one permanent row per heartbeat.

### Safety rule

The sync must be idempotent. If PostgreSQL commits a batch and the HTTP response is lost, retrying the same batch must not credit the student twice.

### Design still to verify in code

The current repository has more than one global activity heartbeat producer in addition to the Study Activity accumulator. These need to be consolidated so the final architecture has one clear Study Hub learning tracker and a separate broader product-activity mechanism.

Before freezing implementation, test:

- switching documents/features;
- inactivity and visibility;
- reload;
- offline/reconnect;
- duplicate sync;
- response lost after commit;
- concurrent sync;
- Nairobi midnight;
- daily 12-hour server ceiling;
- authorization/context validation;
- 400 active students.



## 2026-10-06 — Study Hub implementation notes

The implementation has moved from design into code on main. The backend now accepts an absolute daily Study Hub total and only advances the PostgreSQL total by the forward difference, so retrying the same total is safe. The authenticated user's row is locked before reading/creating/updating the Study Hub row, which serializes concurrent first-sync and update races for one account.

The old per-document heartbeat is retired. Historical StudyTimeLog data is consolidated by migration into one study_hub row per user/day so previous study time is not silently lost. The browser tracker is global across Study Hub learning screens; changing documents or features changes context without creating another clock. The old studyActivity module is only a compatibility facade.

Product analytics remains a separate activity concept. Its CSRF token is cached so the analytics loop no longer fetches /me every minute.

At implementation time this was intentionally not QA-green. The subsequent runtime gate has now passed 6/6. The remaining Study Hub evidence is browser/offline lifecycle behavior and later performance testing; the 400-active-student test remains deferred until functional and browser gates are green.


## 2026-10-06 — Study Hub regression audit

A regression audit was performed after the Study Hub implementation exposed multiple failures that were not adequately protected by CI.

### Findings

1. `scripts/test_study_time_runtime.py` was introduced with the Study Hub work, but no GitHub Actions workflow was running it. The existing realtime runtime workflow covers realtime/calling/chat tests only and uses SQLite, which is not sufficient to prove PostgreSQL `with_for_update()` concurrency semantics.
2. The initial `chat_interactions.py` schema-mutation removal correctly removed runtime PostgreSQL DDL, but also removed the `app` import while Flask request hooks still referenced `@app.before_request`/`@app.after_request`. This caused a real application boot regression (`NameError: app is not defined`). Commit `18ed81a` restores the import without restoring runtime DDL.
3. The Study Hub auth/CSRF runtime test expected `401` for an unauthenticated request, while the route had `@require_csrf` before its in-function authentication check. Because decorators execute first, the observed response was `403`. The route has now been corrected to use `@login_required` before `@require_csrf`, matching the established contract documented by `require_csrf`.
4. Earlier stale PostgreSQL lock chains were traced to obsolete runtime `ALTER TABLE` statements in `chat_interactions.py`, not to the Study Hub reconciliation locking logic itself. Those statements are now removed; Alembic owns the schema.

### Regression-protection changes

- Added PostgreSQL-backed `.github/workflows/study-hub-runtime-regression.yml` to run the full Study Hub runtime suite after canonical Alembic migrations.
- The workflow is path-scoped to the Study Hub backend/runtime test, Alembic/schema, requirements, and workflow itself.
- The Study Hub runtime gate now exercises the same database family required for the production concurrency contract instead of relying on SQLite.

### Freeze status

Still **not green** until the corrected route passes all six runtime tests locally and the new CI workflow completes successfully. No VPS migration or performance freeze should happen before that gate is green.


## 2026-10-06 — Documentation reconciliation: current release truth

The three release documents are now synchronized around one rule: historical notes remain historical, while current status is determined by the latest preserved evidence.

### Current evidence

- Full local PostgreSQL/Alembic QA: **74 passed, 0 failed, 3375 warnings — GREEN**.
- Focused authenticated realtime runtime: **9 passed in 2.98s — GREEN**.
- Focused authenticated calling signaling runtime: **4 passed in 3.31s — GREEN**.
- Redis chat-worker gate: **GREEN**.
- Redis cross-process realtime client delivery: **GREEN**.
- Study Hub runtime reconciliation: **6 passed, 3 warnings — GREEN**.
- Production-style Docker frontend/app build: **GREEN** on the latest verified build.
- Browser-to-browser WebRTC media: **NOT YET PROVEN**.
- Browser/offline Study Hub lifecycle: **NOT YET PROVEN**.
- Storage/backup/restore: **NOT TESTED**.
- Full launch-contract CI after the latest changes: **NOT YET VERIFIED**.
- 400-active-student performance testing: **DEFERRED** until functional/browser gates are green.
- VPS/Render production deployment: **BLOCKED BY THE RELEASE FREEZE GATE**, intentionally.

### Documentation roles

- `actualtest.md` is the evidence ledger: what was actually executed and what each test proves.
- `notes.md` is the learning/engineering diary: why decisions and fixes happened, including historical snapshots.
- `docs/NEXT_STEPS.md` is the current execution plan: remaining work and its present status.

If a historical entry says a gate was pending, that statement describes the state at that time; it must not be interpreted as the latest status when a later evidence entry supersedes it.

### Freeze rule

No VPS migration, GPU purchase, or production launch work should be treated as the next step until the remaining browser/offline, storage/recovery, CI, integration, and final regression gates are complete.


## 2026-10-07 — Repeatable code-traced release QA system
The repository now contains a repeatable QA trace layer in qa/release_manifest.json, verified by scripts/qa_trace.py and gated by .github/workflows/release-qa-trace.yml.

The intent is to stop QA knowledge from living only in chat. Each release-scoped feature declares its frontend entry, backend route/logic, database ownership, runtime/browser tests and CI evidence. The trace verifier checks structural links; runtime tests remain the authority for behavioral correctness.

The current registry records Study Hub, E2EE identity, personal streak and Shared Streak. Shared Streak is explicitly not release-certified until its wiring, canonical schema ownership and runtime lifecycle are proven. E2EE identity has a dedicated gap for the observed 409 identity-replacement lifecycle. Personal streak needs deeper milestone/date-boundary/XP regression.

Current browser evidence was reconciled: the clean two-browser WebRTC gate is GREEN, including real Socket.IO signaling, RTCPeerConnection connection and live remote audio MediaStream tracks. The observed /keys/register 409 remains an E2EE identity lifecycle investigation, not a WebRTC failure.

The repository execution tracker (docs/NEXT_STEPS.md), evidence ledger (actualtest.md), engineering diary (notes.md) and Study Hub design record (designstudytime.md) are being kept synchronized so completed work and remaining work do not depend on conversational memory.


## 2026-10-07 — Persistent release-gate source of truth

The QA process has now been moved from conversation-only tracking into the repository. `qa/release_manifest.json` describes the code execution paths, `scripts/qa_trace.py` checks structural traceability, and `qa/release_status.json` records the current release state and evidence.

This distinction is intentional: a trace proves that we know where a feature executes; it does not prove the feature works. Runtime, browser, integration and CI evidence are still required before a release-scoped feature becomes GREEN.

The current release is **BLOCKED**, not because already-green subsystems are being reopened, but because required gates remain unfinished. Newly confirmed browser WebRTC/media evidence is GREEN. Remaining work is E2EE identity lifecycle, deeper personal streak regression, Shared Streak scope/wiring/certification, browser/offline Study Hub lifecycle, recovery/backup, cross-system journeys, CI verification and final clean regression.

From this point onward, when a gate changes state, update the repository status/evidence records on `main` rather than relying on chat memory. Historical entries remain historical; `qa/release_status.json` is the current machine-readable release truth.

## 2026-10-07 — E2EE gate correction

The first E2EE lifecycle run exposed test-harness issues rather than a confirmed product failure. Runtime cases were sharing a user fixture, cleanup nested a transaction, and the browser reload wait hit Chromium ERR_ABORTED after first-device registration had already passed. The tests were corrected without changing application E2EE behavior. E2EE remains IN PROGRESS until the corrected gates pass.


## 2026-10-07 — Offline content/artifact audit found and fixed a real replay gap

The existing green Study Hub clock test proved local time persistence, but source inspection showed that this was not enough to certify actual document/artifact offline use.

The important distinction is:
**offline metadata/state persistence is not the same as offline content usability.**

The repository's intended Study Hub package already stores complete document Blobs in IndexedDB and copies ready private generated artifacts into the generated-material store. The configured product limits are 75 MB per document, 250 MB total Study Hub document assets, 80 generated-material rows, 512 KiB per generated payload, 25 MB per audio object and 80 MB total audio cache.

The deeper audit found three defects in the artifact replay path:
1. `generationRequest()` checked `selectedMaterialId` before reading it from `prepza-open-material`, so the offline branch could never select the intended cached artifact.
2. `generatedMaterials.ts` rejected `/documents/<id>/materials/<id>` paths even though `studyHubOffline.ts` stored ready artifacts under exactly those paths.
3. Podcast offline save cached the binary audio but not the playback descriptor used by the podcast player to locate that binary cache.

These were corrected directly on `main` without weakening the tests or bypassing entitlement checks. Offline generation remains read-only: only already-ready private artifacts owned by the student are copied, and generation itself still requires connectivity.

New browser gate:
`scripts/test_browser_study_hub_offline_content.py`

It covers multiple documents, all generated material types, podcast binary audio, reload persistence, forbidden offline generation POSTs, and the exact application storage caps. The test is on `main` but still needs to be executed locally against the rebuilt Docker app.


## 2026-10-07 — Offline IndexedDB schema migration fixed before browser gate execution

The first execution of `scripts/test_browser_study_hub_offline_content.py` did not reach the document assertions. Chromium raised `NotFoundError` because `prepza-offline-v2` existed at IndexedDB version 3 with only the `savedStudyHub` object store. The Study Hub module and generated-material module shared the same database/version but each assumed its own stores had already been created. On a fresh first-use sequence, the first opener could therefore leave the other stores missing.

This was classified as a real application persistence/schema defect, not a reason to weaken the browser test. The shared offline database was migrated to version 4. Both offline modules now create all required shared stores during the v4 upgrade: `savedStudyHub`, `generatedMaterials`, and `generatedAudio`. Existing version-3 databases therefore receive the missing stores through the normal IndexedDB upgrade path.

The content/artifact browser gate remains **NOT TESTED** until the rebuilt frontend is exercised locally. This gate must prove the v4 migration and then the full three-document/document-Blob/generated-artifact/podcast/reload/no-generation-POST behavior.


## 2026-10-07 — Admin study-time visibility wired to the same authoritative clock

The admin Operations surface now distinguishes broad activity from actual Study Hub study time. The existing `last_active_at` metrics remain the DAU-style signal for "around Prepza". New admin study metrics read the authoritative `study_time_log` / `StudyTimeLog` records used by the student Profile/Study Activity endpoints.

Admin now receives: students who studied today, students who reached the 10-minute qualifying threshold today, total Study Hub seconds today, total Study Hub seconds across the last seven Nairobi study dates, and a top-50 table of students who are either recently active or have Study Hub time, showing today/7-day study time and last active time. Admin accounts are excluded from student study aggregates. The admin study date is explicitly calculated in `PREPZA_TIMEZONE` (default Africa/Nairobi), not PostgreSQL `CURRENT_DATE`, so the dashboard follows the same Nairobi day boundary as the study-time reconciliation system.

This is an implementation change, not yet a release-certified gate. The next runtime/browser proof must create a known student study total, verify the student's `/study-time` value, then verify the admin Operations response and UI report the same authoritative seconds; it must also cover offline reconciliation, concurrent sync idempotency, the 12-hour daily ceiling, Nairobi midnight, and admin/student separation.


## 2026-10-07 — Admin Study Hub time equality gate prepared

The admin Study Hub time dashboard is now backed by the same authoritative `StudyTimeLog` rows used by the student `/study-time` endpoint. I added `scripts/test_browser_admin_study_time.py`.

The gate covers: 25s online -> offline +20s -> reconnect at 45s; concurrent sync idempotency; the 12-hour ceiling; the Nairobi calendar day; admin exclusion; and two-student isolation. The browser portion uses authenticated Playwright student/admin contexts, while database mutations and concurrency run inside the real Docker app container against PostgreSQL.

While preparing this gate, we also found that `studyHubOffline.ts` declared shared IndexedDB version 4 but was still opening `prepza-offline-v2` at version 3. That could prevent the intended v4 migration when that module opened first. This was fixed on `main`; it now opens at the declared version 4. The offline content/artifact gate remains untested until the rebuilt frontend is exercised.

**Evidence status:** the admin equality gate is not release-certified yet. The test script is on `main` and is ready for local execution after the standard Docker rebuild.

**Interview explanation:** the student profile and admin dashboard should not calculate study time independently. They should read the same authoritative PostgreSQL record, with concurrency-safe reconciliation and the same daily ceiling.

## 2026-10-07 — Admin Study Hub gate: aggregate semantics versus test isolation

The first real execution of `scripts/test_browser_admin_study_time.py` produced four assertion failures and one teardown error. Source tracing showed that the failures did not yet prove a product regression: `admin_operations.py` intentionally computes `study_seconds_today` and `study_seconds_7d` as global sums across all non-admin students. The browser gate had accidentally assumed the local PostgreSQL database contained only its three newly-created fixture users.

The observed mismatches (155 vs 45, 43310 vs 43200, 140 vs 30, and 220 vs 110) are consistent with unrelated/stale student rows contributing to those global aggregates. The 12-hour ceiling is also a **per-student** daily ceiling, not a ceiling on the admin's aggregate across all students.

The correct QA invariant is therefore two-layered: the known fixture student's own admin row must exactly equal the authoritative `StudyTimeLog` value, while the global admin total must change by exactly that student's contribution and admin-account rows must not contribute. The browser gate has been corrected to reset its fixture rows and compare aggregate deltas against a live baseline.

The run also exposed teardown ordering around the deliberate non-cascading `UserKey.user_id` foreign key. The fixture now commits child `UserKey` deletion before loading/deleting the fixture users. This changes only test cleanup ordering; it does not weaken the production account-deletion FK contract.

This is useful release-QA evidence: realistic surrounding database data must not make an otherwise correct aggregate endpoint look wrong, and tests should prove both per-user correctness and aggregate semantics.


## 2026-10-07 — Admin Study Hub browser rerun: navigation path is now the blocker

The corrected admin Study Hub browser gate was rerun from a disposable Docker QA container. It produced **1 passed, 4 failed** after 240.41 seconds. The four failures all timed out in Playwright at `page.goto("http://app:5000/", wait_until="commit")` immediately after a successful `POST /login`.

This is materially different from the earlier test-isolation failures. The corrected fixture cleanup/baseline logic has not yet been exercised by those four cases because browser navigation never commits. Source inspection shows `/` is a Flask route serving the built frontend `index.html`; the next step is to isolate that HTTP document response and determine why Chromium inside the temporary QA container cannot receive the document. No Study Time production logic should be changed merely to make this test pass.

Release evidence remains **IN PROGRESS** for the admin Study Hub visibility gate. The offline content/artifact gate and the other release gates listed in `actualtest.md` remain separate and must continue according to the repository tracker.


## 2026-10-08 — Offline content gate: separate test-fixture defects from product defects

The offline generated-material browser gate has now exposed two different harness inconsistencies before reaching its product assertions.

First, the fixture initially ran database setup with host Python, causing a connection attempt to `127.0.0.1:5432`. Existing browser gates already showed the intended pattern: Playwright runs on the host against `http://localhost:5000`, while database fixtures run through `docker compose exec -T app python -`. That fixture was corrected on main.

Second, the fixture seeded the shared `prepza-offline-v2` IndexedDB database through three concurrent version-3 openers, each creating a different object store. This did not match the production v4 schema lifecycle and produced `NotFoundError` when one transaction requested a store another opener had not created. The fixture is now corrected to open v4 once, create `savedStudyHub`, `generatedMaterials`, and `generatedAudio` together, then seed them sequentially.

Neither of these two failures is evidence that the production app is broken. They are QA-harness failures. However, the earlier discovery that production v3 offline modules could create only part of the shared schema was a genuine product persistence defect and was fixed by the v4 IndexedDB migration. The browser gate remains necessary because code-level schema correctness is not the same as proving an existing v3 browser database upgrades and the full document/artifact/podcast flow works after reload and offline transition.

    
## 2026-10-08 — Offline content gate: second-stage navigation timeout

The fixture corrections allowed the browser gate to reach its first real product-level check:

    PASS: multiple saved documents remain listed offline

The next step failed with:

    Locator.wait_for: Timeout 15000ms exceeded
    waiting for get_by_role("button", name="Continue Reading", exact=True) to be visible

I traced this against the current production flow before changing application code. The My Study document entries are real button controls whose click handler sets activeDocumentId and opens document-study. The DocumentStudyHubScreen then loads the saved offline package and renders the real Continue Reading button; the native DocumentReaderScreen is the component that subsequently proves the Blob-backed reader with OFFLINE / Offline study copy.

Because the test timed out before those reader assertions, this run does not prove a production offline-reader failure. The browser test was too opaque about which UI state it had reached. The test has now been corrected to click the actual document-row button and dump the rendered page body when Continue Reading is still absent.

**Production-impact classification:** currently unclassified / not proven. Do not change production navigation or offline persistence based on this timeout alone. The next run must identify the actual rendered state first.

## 2026-10-08 — Offline content gate: final navigation-layer diagnosis

The newest failure was:

    waiting for locator("button").filter(has_text="Offline Economics Notes").first

This is not an offline-cache or generation failure. The test had already proved that all three saved documents remained listed offline. The failure occurred because the offline reader Back button returns to the document Study Hub, not directly to the parent Study Materials list.

The corrected test now follows the actual production navigation hierarchy: reader -> document Study Hub -> My Study -> document list.

The generated-material objective remains unchanged: artifacts are seeded as already-ready local records, the browser is taken offline, and the existing material replay screens must resolve those cached payloads without sending any generation POST request. This gate is about offline persistence/replay, not offline generation.


## 2026-10-10 — Offline content gate: worker startup race and offline replay logic audited

The user rebuilt and ran the content/artifact browser gate at commit `4f1ed663`. It stopped at:

    FAIL: Page.evaluate: Execution context was destroyed, most likely because of a navigation

The failing evaluate is the asynchronous IndexedDB fixture seed; the test did not reach its material replay assertions. This is recorded as **blocked before product assertions**, not as a feature failure.

I compared the exception with the actual service-worker implementation. The worker calls `skipWaiting()` on install and `clients.claim()` during activation; the registration script responds to `controllerchange` with `window.location.reload()`. The test had an arbitrary 1.2-second delay after `page.goto`, so fixture seeding could overlap that full document reload. The gate now records navigation events and requires the source-described same-origin startup reload plus service-worker control before running the seed. It also waits for document rows instead of reading the page immediately after the tabs render.

That source review exposed a separate real app defect: the four standard material screens requested `/me` before calling `generationRequest()`. Offline `/me` failure prevented the cached-material branch from being reached. The offline selection matcher also treated UI type `summary` as different from route feature `summarize`; the offline response was keyed as `summarize`, while SummaryScreen reads `summary`. The current main changes normalize these aliases, replay the exact selected ready artifact without auth/network lookup, and prohibit a generation POST fallback while offline. I also adjusted the Mind Map fixture to seed a string branch because the current renderer expects `branches: string[]`, not `{label: ...}` objects.

No release PASS is claimed: these source/test changes need a rebuilt local browser run. Required evidence remains successful replay of Summary, Flashcards, Practice Questions, Mind Map and Podcast after offline transition and reload, with zero generation POSTs.
