# Prepza Infrastructure & Engineering Learning Guide

Purpose: a beginner-friendly but technically accurate guide to the infrastructure, backend, database, deployment, security, and DevOps vocabulary used by Prepza.

Repository basis: Prepza main, with the local Docker/Alembic milestone verified on 2026-10-03.

Rule: when this guide says Prepza currently does something, it is based on repository code/configuration, not a future assumption.

## 1. How to study this

Study in this order:

1. Computer/server fundamentals
2. Linux and networking
3. Docker
4. Prepza application stack
5. PostgreSQL
6. SQLAlchemy and Alembic
7. Redis and realtime
8. Gunicorn and web serving
9. Storage, email, payments, AI
10. Git and CI/CD
11. Security
12. Monitoring and scaling
13. Kubernetes
14. Self-hosting Prepza
15. Engineering-meeting vocabulary

For every technology ask:
- What is it?
- Why does Prepza need it?
- Where does it run?
- What happens if it fails?

That mental model is more useful than memorizing definitions.

## 2. The big picture

A web application lets a user's device communicate with software running elsewhere.

~~~
Student browser
      |
      | HTTPS
      v
React / TypeScript PWA
      |
      | API requests
      v
Flask backend
      |
      +------ PostgreSQL
      +------ Redis
      +------ OpenAI
      +------ Paystack
      +------ AWS SES
      +------ R2-compatible storage
      +------ Kokoro worker
~~~

The browser is the client. The backend and infrastructure provide the services behind it.

## 3. CPU, RAM, storage and GPU

### CPU
CPU means Central Processing Unit. Think of it as the computer's worker. CPU matters for calculations, Python execution, database work, PDF/audio processing and other computation.

### vCPU
A cloud provider's vCPU is a virtualized CPU execution unit. Four vCPU does not necessarily mean four physical CPU chips.

### RAM
RAM is short-term working memory.

Think:
- CPU = worker
- RAM = desk space

If RAM is exhausted, processes can slow down, be killed, or fail.

### Disk
Disk is long-term storage. SSD and NVMe are common fast storage technologies. Disk is different from RAM.

### NVMe
NVMe is a fast storage protocol commonly used with SSDs.

### GPU
A GPU is designed for highly parallel computation. Prepza's Kokoro podcast path can use a GPU.

### VRAM
VRAM is GPU memory. An RTX A2000 with 6 GB has 6 GB of VRAM. A 16 GB GPU can fit models/workloads that a 6 GB GPU cannot.

## 4. Processes and services

A process is a running program.

A service is a program or capability intended to keep running or provide functionality to another component.

Prepza's Docker Compose stack has:
- postgres
- redis
- app
- realtime

## 5. Ports

A port is a numbered network door.

Common examples:
- PostgreSQL: 5432
- Redis: 6379
- HTTP: 80
- HTTPS: 443

Prepza locally exposes:
- 127.0.0.1:5000 -> app
- 127.0.0.1:5001 -> realtime

## 6. localhost, IP addresses and DNS

localhost means this computer. 127.0.0.1 is the common IPv4 localhost address.

An IP address identifies a network destination.

DNS translates a human-friendly domain into a network destination.

Conceptually:

~~~
prepza.example.com
        |
        v
       DNS
        |
        v
   server address
~~~

## 7. HTTP and HTTPS

HTTP is the normal web communication protocol.

HTTPS is HTTP protected by TLS encryption.

Production Prepza should use HTTPS.

## 8. Frontend

Prepza's frontend is a React/TypeScript Progressive Web App.

It handles:
- pages and components
- navigation
- forms
- offline browser storage
- chat UI
- study UI
- browser-side E2EE key handling
- API calls
- Socket.IO connections

The frontend lives under frontend/.

## 9. React

React is the UI library used by the frontend.

It lets the interface be built from reusable components rather than one enormous page.

React runs primarily in the user's browser. It is not Flask and it is not PostgreSQL.

## 10. TypeScript

TypeScript adds static types to JavaScript.

Example idea:

~~~text
function add(a: number, b: number): number
~~~

The types help catch certain mistakes before runtime.

## 11. Node.js and pnpm

Node.js lets JavaScript programs run outside the browser. Prepza uses Node tooling during its frontend build.

pnpm is the frontend package manager. Prepza's Docker build uses a frozen lockfile so dependency installation is reproducible.

Important: Node.js does not replace Python in Prepza. It is primarily part of the frontend/build toolchain.

## 12. Vite

Vite is the frontend development/build tool. It helps run the development server, transform TypeScript, bundle assets and produce the production frontend distribution.

## 13. Python

Python is Prepza's main backend language.

The Flask application, database models, AI orchestration, payment flows, storage helpers and many backend services are Python code.

The current Docker runtime uses Python 3.13.

## 14. Flask

Flask is Prepza's Python web framework.

Conceptually:

~~~
Browser
  |
  | HTTP
  v
Flask route
  |
  v
Python logic
  |
  +--> database
  +--> provider
  +--> service
~~~

Flask is the web/API layer.

## 15. Gunicorn

Gunicorn is a production Python application server.

Conceptually:

~~~
Network request
      |
      v
   Gunicorn
      |
      v
    Flask
      |
      v
 Python code
~~~

Prepza's current realtime command is:

~~~text
gunicorn -k gthread -w 1 --threads 100 realtime_server:app
~~~

This means one gthread worker process with 100 threads. It is the repository's current configuration, not a universal optimal setting.

## 16. WSGI

WSGI is a standard interface between Python web applications and application servers.

app:app means the app module and its Flask application object. realtime_server:app similarly identifies the realtime module and application object.

## 17. Docker

Docker packages software into containers.

Think:

> Docker gives an application its own little box containing what it needs to run.

Without Docker, coordinating Python, Python packages, Node, pnpm, ffmpeg, PostgreSQL and Redis manually is more difficult.

## 18. Docker image vs container

An image is the packaged blueprint.

A container is a running instance of that image.

~~~
Dockerfile
   |
   v
Docker image
   |
   v
running container
~~~

## 19. Dockerfile

A Dockerfile describes how an image is built.

Prepza's Dockerfile has a frontend-build stage and a Python runtime stage.

Conceptually:

~~~
source code
   |
   v
Node frontend build
   |
   v
frontend/dist
   |
   v
Python runtime image
   |
   +-- Python dependencies
   +-- Prepza code
   +-- frontend build
~~~

This is a multi-stage build.

## 20. Docker Compose

Docker Compose defines multiple containers together.

Prepza's docker-compose.vps.yml currently defines:
- PostgreSQL
- Redis
- app
- realtime

Compose manages:
- containers
- networks
- volumes
- environment variables
- startup dependencies
- port mappings
- health checks

## 21. Docker networks

Containers in one Compose project can communicate through the Compose network.

Inside the Compose network, the application can reach services by names such as:
- postgres:5432
- redis:6379

That is different from your Windows host using 127.0.0.1.

## 22. Docker volumes

A volume stores persistent data outside a container's temporary filesystem.

Prepza defines postgres_data and redis_data.

This is why docker compose down normally does not mean delete the database.

docker compose down -v removes the Compose volumes. We deliberately used that during local recovery because the local database was disposable.

Never casually use down -v against important data.

## 23. Environment variables

Environment variables provide configuration outside the source code.

Examples:
- DATABASE_URL
- REDIS_URL
- OPENAI_API_KEY
- PAYSTACK_SECRET_KEY
- BASE_URL

Think:
- Code = instructions
- Environment = configuration and secrets
- Database = persistent application state

Secrets should not be committed to Git.

## 24. PostgreSQL

PostgreSQL is Prepza's primary structured database.

Think of it as an organized warehouse:

~~~
Database
  |
  +-- tables
       |
       +-- rows
       +-- columns
~~~

## 25. Tables, rows and columns

A user table might look like:

~~~text
id | email | display_name
---+-------+-------------
1  | a@x   | Arnold
2  | b@x   | Jane
~~~

Table = user. Row = one record. Column = one property.

## 26. Primary keys

A primary key uniquely identifies a row.

For example:

~~~text
user.id = 123
~~~

Other records can reference it.

## 27. Foreign keys

A foreign key connects records between tables.

For example:

~~~text
student_order.user_id
        |
        v
user.id
~~~

This lets PostgreSQL enforce relationships.

## 28. Indexes

An index helps PostgreSQL find rows faster.

Think of a library catalog: without it, search may require checking every book; with it, the database can jump toward relevant rows.

Indexes improve some reads but consume storage and add work to writes. More indexes is not automatically better.

## 29. Constraints

Constraints tell the database what is allowed.

Examples:
- primary key
- foreign key
- unique
- not null
- check

Constraints can protect data even when application code has a bug.

## 30. Sequences

A sequence generates values, often numeric IDs.

Example:

~~~text
1, 2, 3, 4, 5...
~~~

## 31. Transactions

A transaction groups database operations into one logical unit.

The useful mental model is:

> Either the logical operation succeeds, or the database should not be left halfway through it.

Transactions are a major part of safe database operations.

## 32. SQLAlchemy

SQLAlchemy is the Python database toolkit/ORM used by Prepza.

Conceptually:

~~~
Python
  |
  v
SQLAlchemy
  |
  v
SQL
  |
  v
PostgreSQL
~~~

It is not primarily Python-to-JavaScript communication.

The real Prepza chain is:

~~~
React/TypeScript
       |
       | HTTP
       v
Flask/Python
       |
       v
SQLAlchemy
       |
       v
PostgreSQL
~~~

## 33. ORM

ORM means Object-Relational Mapping.

It lets application code represent database records as Python objects.

The ORM does not eliminate the need to understand SQL or database design.

## 34. Alembic

Alembic manages database schema migrations for SQLAlchemy projects.

Think:

> Git history for database schema.

Git tracks code history. Alembic tracks schema history.

~~~
baseline
   |
   v
user_model
   |
   v
future migration
~~~

## 35. What we just achieved with Alembic

We reconstructed a schema-only local baseline from the verified Supabase public schema.

Then we added a main-specific User model compatibility migration.

A fresh local database now follows:

~~~
Empty PostgreSQL
       |
       v
20261002_baseline
       |
       v
20261002_user_model
       |
       v
current local schema
~~~

Verified locally:
- Alembic revision = 20261002_user_model
- public table count = 108
- PostgreSQL healthy
- Redis healthy
- app started
- realtime started

The 108 count includes the Alembic bookkeeping table in addition to the application schema extracted for the baseline.

## 36. Alembic autogenerate

After a model/schema change:

~~~text
alembic revision --autogenerate -m "describe the change"
~~~

Then inspect the generated migration and apply it:

~~~text
alembic upgrade head
~~~

Autogenerate is a candidate generator, not approval.

Some SQL-only functions/triggers still require explicit migration code.

## 37. Alembic head

head means the latest revision in the migration graph.

alembic upgrade head means bring a database through all required revisions until the latest revision.

## 38. Alembic stamp

alembic stamp revision records a migration state without executing that migration.

It is only safe after independently verifying that an existing database already matches the claimed schema.

## 39. Redis

Redis is a fast in-memory data system commonly used for:
- caching
- sessions
- queues
- rate limiting
- realtime coordination

Prepza uses Redis when configured for realtime/message-queue fan-out, presence and the chat-event path.

Redis is not a replacement for PostgreSQL.

Think:
- PostgreSQL = durable structured truth
- Redis = fast shared state/coordination

## 40. Queues and workers

A queue is a waiting line for work.

~~~
Producer
   |
   v
Queue
   |
   v
Worker
~~~

Prepza's chat event path uses Redis Streams with consumer groups and recovery behavior.

The general document AI generation path is different: it currently creates an AiJob and starts a process-local daemon thread. If the web process dies, the thread disappears even though the database job row can remain. Stale-job recovery and generation idempotency reduce the damage, but this is not the same as a durable external worker queue.

Podcast audio uses a separate worker/control architecture.

## 41. Socket.IO and realtime

Socket.IO provides realtime communication.

Prepza uses:

~~~
Browser
   |
   | Socket.IO
   v
realtime_server.py
~~~

PostgreSQL/HTTP persistence remains the source of truth for persisted chat data. Redis can coordinate realtime behavior across instances.

## 42. Reverse proxy

A reverse proxy sits in front of the application.

Typical production shape:

~~~
Internet
   |
   v
HTTPS / reverse proxy
   |
   +--> Flask
   +--> realtime
   +--> frontend/static content
~~~

Common reverse proxies include Nginx and Caddy.

They can handle TLS, routing, headers and public connection handling.

## 43. TLS and HTTPS

TLS provides encryption for HTTPS.

Production Prepza should expose public traffic through HTTPS rather than plain HTTP.

## 44. Object storage and R2

PostgreSQL is not ideal for every large binary file.

Object storage is designed for:
- PDFs
- MP3s
- images
- generated files

Prepza has an R2-compatible storage abstraction and still retains Supabase Storage fallback paths.

## 45. Presigned URLs

A presigned URL is a temporary URL granting controlled access to an object.

Conceptually:

~~~
Backend
   |
   | creates temporary signed URL
   v
Browser
   |
   v
private object storage
~~~

The browser does not need the permanent storage secret.

## 46. AWS SES

SES is Amazon's email service.

Prepza has an SES path for transactional email such as verification and password recovery.

Code integration does not prove live sender verification or delivery. Those require real environment testing.

## 47. Paystack

Paystack provides payment functionality.

Prepza has payment records, subscription/entitlement logic and Paystack flows.

Live verification still requires real provider configuration and controlled testing.

## 48. OpenAI and AI architecture

Prepza's current AI provider boundary is OpenAI-only.

The AI layer includes:
- model/task routing
- cost accounting
- quota handling
- reusable artifacts
- generation fingerprints
- concurrency/lease logic

The application talks to an AI service boundary rather than scattering provider logic throughout every feature.

## 49. AI artifact reuse

Prepza fingerprints generation requests using relevant inputs such as:
- source content hash
- material type
- parameters
- prompt/schema versions
- privacy scope/owner where applicable

If an exact ready artifact exists, the system can reuse it instead of performing another provider generation.

This is important for cost and duplicate prevention.

## 50. Kokoro worker architecture

Podcast audio is separated from the main Flask process.

~~~
Flask control plane
        |
        v
      AiJob
        |
        v
Kokoro worker
        |
        v
     GPU/CPU
        |
        v
     MP3 audio
        |
        v
        R2
~~~

The worker claims jobs, synthesizes speaker turns, performs duration correction/verification and uploads completed audio.

The repository contains GPU autoscaling safety code, but its example configuration remains dry-run/manual. Code existing does not mean a GPU is running or charging.

## 51. Git and GitHub

Git is version control. A commit is a recorded change/snapshot.

GitHub hosts the Git repository and adds collaboration and automation features.

Your Prepza workflow uses direct changes on main rather than unnecessary feature branches.

## 52. CI and CD

CI means Continuous Integration: automated checks on code changes.

Prepza's CI surface covers frontend build, student contracts, admin routes, B2B, realtime, E2EE, AI, Kokoro and other launch contracts.

A passing CI run means the tested contracts passed. It does not prove live provider credentials, backups, production capacity or a working production server.

CD means automating delivery/deployment from tested code into an environment.

## 53. VPS

VPS means Virtual Private Server.

Think:

> A rented virtual computer.

You receive CPU, RAM, disk and network access, but you are responsible for much more of the operating environment than on a managed platform.

## 54. Managed platform vs VPS

Managed platform:
> Run my application for me.

VPS:
> Give me a computer and let me operate it.

Neither is universally better.

## 55. Health checks

A health check asks whether a service is functioning.

A process being alive does not necessarily mean the application is healthy.

## 56. Logs, metrics and traces

Logs = individual events and messages.

Metrics = numerical measurements over time, such as CPU, RAM, latency, error rate and queue depth.

Traces = the journey of a request through multiple components.

Together they form a major part of observability.

## 57. Sentry

Sentry is an error monitoring service. Prepza has a Sentry integration.

Again, integration in code is not proof that the production Sentry configuration has been verified.

## 58. Authentication vs authorization

Authentication:
> Who are you?

Authorization:
> What are you allowed to do?

They are different.

## 59. Sessions

A session lets the application remember that a user is authenticated.

Prepza has session-version logic so old sessions can be invalidated when the account version changes.

Socket authentication uses related account/session checks.

## 60. Hashing vs encryption

Hashing:
> input -> one-way digest

Encryption:
> plaintext -> encrypted data -> recoverable plaintext

Prepza uses SHA-256 content hashing for document-content identity.

## 61. E2EE

E2EE means End-to-End Encryption.

Prepza's current documented E2EE boundary is single-device per account. The private identity key remains on the browser/device.

Multi-device E2EE is a future protocol design rather than a hidden change to the current protocol.

## 62. RLS

RLS means PostgreSQL Row Level Security.

It lets the database enforce which rows a role can access.

It is powerful, but enabling it without policies can break application access. Production RLS work must therefore be designed and verified rather than enabled blindly.

## 63. Common web security terms

SQL injection = malicious input being turned into unintended SQL.

XSS = malicious script being executed in another user's browser.

CSRF = tricking an authenticated browser into making an unwanted request.

Secrets = API keys, passwords, signing keys and other sensitive credentials. Do not commit them to Git.

## 64. Scaling

Vertical scaling = make one machine bigger.

Horizontal scaling = add more application instances.

~~~
Vertical:
4 GB -> 8 GB -> 16 GB

Horizontal:
1 app -> 3 apps -> 10 apps
~~~

Horizontal scaling usually requires shared state and coordination.

## 65. Load balancer

A load balancer distributes incoming traffic among application instances.

~~~
          Load balancer
          /     |     \
        App1   App2   App3
~~~

## 66. Connection pool

Database connections consume resources.

A connection pool keeps a controlled number available for reuse.

"The connection pool is exhausted" means the application cannot obtain the database connection capacity it currently needs.

## 67. Rate limiting

Rate limiting restricts request frequency.

It helps with abuse, accidental request storms and uncontrolled provider usage.

Prepza includes Flask-Limiter.

## 68. Backpressure

Backpressure means slowing producers when consumers cannot keep up.

If 1,000 jobs arrive but workers can only process 20 per minute, the queue grows. The system needs controls instead of unlimited memory/cost growth.

## 69. Bottleneck

A bottleneck is the component limiting overall performance.

Possible bottlenecks:
- CPU
- RAM
- database
- disk
- network
- provider API
- queue worker capacity

## 70. CPU-bound vs I/O-bound

CPU-bound = computation is the limiting factor.

I/O-bound = waiting for database, network or disk is the limiting factor.

Adding RAM does not automatically solve a CPU bottleneck, and adding CPU does not automatically solve slow network I/O.

## 71. Stateless vs stateful

A stateless application instance does not depend on local instance memory/disk for important persistent state.

Stateful systems own or persist important state.

PostgreSQL is stateful. An application designed around external PostgreSQL/Redis/object storage can be easier to scale horizontally.

## 72. Idempotency

An operation is idempotent when retrying it does not create unwanted duplicate effects.

This is critical for:
- payments
- webhooks
- AI generation
- job retries

Prepza's generation fingerprints and duplicate-collapse mechanisms help here.

## 73. Race condition

A race condition occurs when concurrent operations produce a result dependent on timing.

Example:

~~~
Request A: artifact does not exist
Request B: artifact does not exist
A generates
B generates
duplicate cost
~~~

Generation-family collapse and database-backed coordination help prevent this.

## 74. Atomic operation

An atomic operation is treated as one indivisible logical operation.

Transactions and row locking are important tools for safe concurrent database work.

## 75. Kubernetes

Kubernetes orchestrates containers across machines.

Docker answers:
> How do I package/run this container?

Kubernetes answers:
> How do I operate many containers reliably across a cluster?

Kubernetes vocabulary:
- cluster = whole Kubernetes environment
- node = machine in the cluster
- pod = basic execution unit containing one or more containers
- deployment = desired state for application pods
- replica = another running copy
- service = stable networking for pods
- ingress = external HTTP/HTTPS routing
- namespace = logical separation
- ConfigMap = non-secret configuration
- Secret = sensitive configuration
- PersistentVolume = persistent storage
- rolling deployment = gradually replace old instances with new ones

Prepza does not need Kubernetes merely because Kubernetes exists.

## 76. Containers vs virtual machines

A virtual machine provides a full guest operating-system environment.

A container shares the host kernel while isolating application processes/resources.

Containers are generally lighter than full VMs.

## 77. Deployment

Deployment means making a specific application version available in an environment.

A serious deployment can involve:
1. selecting a commit
2. building an image
3. configuring infrastructure
4. applying migrations
5. starting services
6. health checks
7. functional verification

Deployment is not merely uploading code.

## 78. Rollback

Rollback means returning to a known previous version after a bad deployment.

Database rollback is more complicated than application rollback because schema changes can be destructive. This is why backups and tested migration procedures matter.

## 79. Backup and restore

Backup:
> Create a recoverable copy.

Restore:
> Prove you can recover from that copy.

A backup that has never been restored is weak evidence of recoverability.

Prepza has PostgreSQL backup tooling that creates a custom-format dump and verifies the archive with pg_restore --list. External backup storage and a completed restore drill remain future work.

## 80. Disaster recovery

RPO = Recovery Point Objective: how much data loss is acceptable.

RTO = Recovery Time Objective: how long recovery may take.

These are operational targets.

## 81. Availability

Availability describes how consistently a service can be used.

Do not promise a percentage without measuring real infrastructure reliability.

## 82. Latency and throughput

Latency = delay.

Throughput = amount of work completed per unit time.

A system can have good latency for one request and still perform badly under high concurrency.

## 83. Load testing

Load testing generates controlled traffic/work to find capacity and bottlenecks.

Useful Prepza measurements:
- CPU
- RAM
- PostgreSQL connections
- database latency
- Redis usage
- request latency
- errors
- AI queue depth
- worker capacity

The correct question is not "How many users does Prepza support?" without a workload definition.

The useful question is:
> Under this workload and infrastructure configuration, where does the system bottleneck?

## 84. RAM and production capacity

If an 8 GB machine runs the OS, PostgreSQL, Redis, Flask, realtime, Docker and other processes, all of them compete for memory.

Any example RAM allocation is illustrative, not a capacity measurement.

The correct rule is:

> More RAM should be justified by measurements, not guesses.

## 85. Control plane and worker

A control plane coordinates work.

A worker performs work.

Prepza's Kokoro path is a clear example:

~~~
control plane
      |
      v
    jobs
      |
      v
   worker
      |
      v
 generated audio
~~~

This allows expensive workers to scale independently.

## 86. Blue-green deployment

Blue is the current production version. Green is the new version.

Traffic can be switched after the green version is verified.

It can reduce some deployment risks but requires extra infrastructure.

## 87. Canary deployment

A canary sends a small portion of traffic to the new version before broader rollout.

The percentages are deployment policy decisions, not universal constants.

## 88. Feature flag

A feature flag lets code exist without exposing it to everyone.

Useful for gradual rollout, testing and emergency disablement.

## 89. Prepza's current dependency map

~~~
Student browser
   |
   +--> React / TypeScript PWA
   |       +--> IndexedDB / Cache Storage
   |       +--> Socket.IO client
   |       +--> browser E2EE handling
   |
   +--> Flask application
           +--> PostgreSQL via SQLAlchemy
           +--> Redis when configured
           +--> OpenAI
           +--> Paystack
           +--> SES
           +--> R2-compatible storage
           +--> realtime server
           +--> Kokoro control
                    |
                    v
               Kokoro worker
                    |
                    v
                  GPU/CPU
~~~

## 90. Example: student uploads a document

Conceptually:

~~~
student selects PDF
       |
       v
React frontend
       |
       v
Flask
       |
       +--> storage
       |
       +--> PostgreSQL metadata
       |
       v
DocumentContent / Document
       |
       v
SHA-256 content identity
~~~

File bytes and structured metadata have different jobs.

## 91. Example: student generates a summary

Conceptually:

~~~
student request
      |
      v
Flask
      |
      v
quota/economics checks
      |
      v
source content identity
      |
      v
exact artifact lookup
    /   \
 found  missing
  |       |
  |       v
  |    generation
  |       |
  |     OpenAI
  |       |
  +---<---+
      |
      v
generated artifact
~~~

The actual implementation also includes fingerprints, leases, privacy scope, jobs and recovery.

## 92. Example: podcast generation

~~~
AI script
   |
   v
podcast job
   |
   v
Kokoro worker
   |
   v
speaker turns
   |
   v
FFmpeg/pydub
   |
   v
duration verification
   |
   v
R2
~~~

The GPU worker is separate from Flask.

## 93. Local vs production

Local:

~~~
your laptop
   |
   v
Docker
   +-- PostgreSQL
   +-- Redis
   +-- Flask
   +-- realtime
~~~

Production adds public networking, HTTPS, secrets, backups, monitoring, provider credentials, recovery procedures and measured capacity.

Production is not simply "run Docker on a bigger computer."

## 94. Self-hosting Prepza: the layers

1. Machine: CPU, RAM, disk, network, OS
2. Security: SSH, firewall, users, secrets
3. Docker: engine, Compose, images, volumes, networks
4. Data: PostgreSQL, Redis, backups, restore
5. Application: Flask, Gunicorn, realtime, frontend
6. Public access: DNS, reverse proxy, HTTPS
7. Providers: OpenAI, R2, SES, Paystack, OAuth if enabled, Sentry
8. Workers: Kokoro, queues, GPU lifecycle
9. Operations: logs, metrics, alerts, load testing, rollback

## 95. Engineering meeting vocabulary

"Check the logs."
> Something happened; inspect recorded runtime events.

"The service isn't healthy."
> The process may be alive, but its health check is failing.

"The container is restarting."
> The application inside may be crashing or being killed.

"The DB connection pool is exhausted."
> The app needs more database connection capacity than is currently available.

"We're CPU-bound."
> CPU is limiting performance.

"We're memory-bound."
> RAM is limiting performance.

"The queue is backing up."
> Work is arriving faster than workers can process it.

"We need backpressure."
> Prevent uncontrolled work growth.

"Make it idempotent."
> Retrying must not create unwanted duplicates.

"We need a migration."
> The database schema needs a controlled versioned change.

"Stamp the database."
> Record a migration version without executing that migration.

"Don't stamp blindly."
> Verify the existing schema first.

"Put it behind a reverse proxy."
> Put an HTTPS/routing layer in front of the application.

"Scale horizontally."
> Add application instances.

"Scale vertically."
> Give the existing machine more resources.

"We need a worker."
> Move asynchronous/expensive work out of the request path.

"The pod died."
> A Kubernetes execution unit stopped and may be replaced.

"The deployment rolled back."
> Return to a previous application version.

"The database is the source of truth."
> This system is authoritative for that persistent information.

"The provider is rate limiting us."
> The external service is restricting request frequency.

"We hit the quota."
> A configured allowance has been exhausted.

"We need observability."
> We need enough logs, metrics and traces to understand the system.

## 96. Beginner's mental dictionary

| Word | Think |
|---|---|
| CPU | worker |
| RAM | desk space |
| Disk | filing cabinet |
| GPU | parallel worker |
| VRAM | GPU desk |
| IP | network address |
| DNS | internet phonebook |
| Port | numbered door |
| HTTP | web conversation |
| HTTPS | encrypted web conversation |
| Process | running program |
| Service | continuously useful program |
| Docker | application box |
| Image | box blueprint |
| Container | running box |
| Compose | multiple-box manager |
| Volume | persistent box storage |
| Python | backend language |
| Flask | Python web framework |
| Gunicorn | Python application server |
| React | frontend UI library |
| TypeScript | typed JavaScript |
| Node | JavaScript runtime/tooling |
| pnpm | frontend package manager |
| PostgreSQL | structured database |
| SQLAlchemy | Python/database bridge |
| Alembic | database schema history |
| Redis | fast shared state/queue/cache |
| Socket.IO | realtime communication |
| R2 | object/file storage |
| SES | email service |
| Paystack | payment service |
| OpenAI | AI provider |
| Worker | background job processor |
| Queue | waiting line for work |
| Reverse proxy | front door |
| VPS | rented virtual computer |
| CI | automated code checks |
| CD | automated delivery/deployment |
| Kubernetes | container orchestrator |
| Logs | event history |
| Metrics | numerical measurements |
| Traces | request journey |
| Backup | recoverable copy |
| Restore | recovery from copy |
| RPO | acceptable data loss |
| RTO | acceptable recovery time |
| Horizontal scaling | more instances |
| Vertical scaling | bigger instance |
| Idempotency | safe retry |
| Bottleneck | limiting component |
| Latency | delay |
| Throughput | work per time |

## 97. What you should be able to explain

Before talking to an infrastructure engineer, aim to explain these in your own words:

1. Prepza has a React/TypeScript frontend.
2. Flask is the primary Python backend.
3. SQLAlchemy connects the backend to PostgreSQL.
4. Alembic controls new database schema migrations.
5. Redis provides configured realtime/chat coordination and related fast state.
6. Socket.IO provides realtime transport.
7. R2 is the intended object-storage path.
8. SES handles transactional email.
9. Paystack handles payments.
10. OpenAI is the current AI provider boundary.
11. Kokoro audio generation is a separate worker path.
12. Docker packages the application/services.
13. PostgreSQL must be backed up and restore-tested.
14. CI proves tested contracts, not live infrastructure.
15. Production capacity must be measured.

## 98. The local milestone we just proved

Current local environment:

~~~
Windows laptop
    |
    v
Docker Desktop
    |
    +-- PostgreSQL 17
    +-- Redis 8
    +-- Prepza Flask app
    +-- Prepza realtime
~~~

Database migration state:

~~~
20261002_baseline
        |
        v
20261002_user_model
~~~

Verified:
- Alembic version = 20261002_user_model
- public table count = 108
- PostgreSQL healthy
- Redis healthy
- app started
- realtime started

## 99. The migration incident as an engineering lesson

We first saw "relation user does not exist." That showed the local PostgreSQL database lacked the base schema.

We introduced the Alembic baseline.

The first attempt exposed literal newline corruption in the baseline SQL.

We corrected it.

The next attempt reported that ada_request_usage already existed.

Instead of guessing, we inspected the database and discovered 15 historical Prepza tables.

We deliberately removed the disposable local Docker volumes, created a clean PostgreSQL instance and reran the migration.

The clean migration succeeded.

The lesson is:

> Inspect first. Change second.

## 100. What remains

The project is moving from:

> Can the code and local infrastructure run?

toward:

> Can we prove the complete production system works safely?

Remaining work includes:
- local endpoint/functional verification
- full CI re-verification after latest changes
- local backup/restore
- Render deployment verification when capacity is available
- real PostgreSQL/Redis production verification
- R2 upload/read/delete testing
- SES verification
- Paystack verification
- backup/restore rehearsal
- production migration procedure
- HTTPS/reverse proxy/security
- measured load testing
- CPU/RAM/database/Redis capacity evidence
- monitoring and alerts
- controlled rollout
- deliberate self-hosting decision only if measured requirements justify it

The persistent execution tracker in docs/NEXT_STEPS.md is the checklist for this work.

## 101. Final lesson

Infrastructure is not a collection of scary words. It is a collection of responsibilities.

~~~
Computer
  |
  +-- compute
  +-- memory
  +-- storage
  +-- network
        |
        v
Operating system
        |
        v
Containers
        |
        +-- application
        +-- database
        +-- cache/queue
        |
        v
Public networking
        |
        v
External services
        |
        v
Monitoring + backups + recovery
~~~

Once each layer has a clear responsibility, Docker, PostgreSQL, Redis, Kubernetes, Gunicorn, reverse proxies, workers, queues and autoscaling stop sounding like random jargon.

They become names for specific jobs.

Study slowly. You are not expected to learn everything at once.
