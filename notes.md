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