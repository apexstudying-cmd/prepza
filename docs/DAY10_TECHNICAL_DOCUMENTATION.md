# Day 10 — verified technical documentation

Date: 2026-10-01

Audited source checkpoint: b63df1045c6643c0495b53b355873a5c14f986ef

This document is an implementation reference. It intentionally distinguishes:

- Implemented: directly represented by source code, configuration, or tests in the audited repository.
- Scaffolded: code exists, but the external infrastructure/provider has not been proven live.
- Not currently implemented: the repository does not contain the claimed capability.
- Future: explicitly described as a later change in repository documentation.

It must not be read as a claim that production deployment has been completed.

## 1. System boundary

The current repository is a monolithic Flask application plus a React/TypeScript PWA, with separate worker components where the code explicitly defines them.

~~~text
Browser
  |
  | HTTPS / fetch
  v
Flask app (app.py)
  |
  +-- SQLAlchemy --> PostgreSQL
  |
  +-- AI layer --> OpenAI
  |
  +-- Payment layer --> Paystack
  |
  +-- Email layer --> AWS SES
  |
  +-- Storage helpers --> R2 when configured
  |                         Supabase fallback paths remain
  |
  +-- Socket.IO --> realtime_server.py
  |                    |
  |                    +--> Redis message queue when configured
  |                    +--> direct single-instance fallback otherwise
  |
  +-- Kokoro control API --> standalone Kokoro worker
                                |
                                +--> local Kokoro TTS
                                +--> R2 audio object
~~~

The frontend separately maintains browser-local offline state and cryptographic material.

## 2. Frontend implementation

frontend/package.json declares React 19, React DOM 19, Socket.IO client 4.8.1, Tailwind CSS 4, TypeScript 5.7, Vite 8.0.16, and pnpm 10.34.3.

The package scripts are significant:

- dev: Vite on 0.0.0.0
- prebuild: a large repository transformation/audit chain
- build: TypeScript check, Vite build, then repository audit scripts
- preview: Vite preview
- format: oxfmt

The prebuild behavior is intentional in the current repository. It should not be documented as a conventional no-op prebuild hook.

The repository contains a PWA manifest, service worker, service-worker registration, offline fallback HTML, and 192px/512px icons.

## 3. Main frontend domains

frontend/src/ contains:

- application shell and onboarding;
- generation screens and usage-plan presentation;
- Study Activity;
- organisation discovery and organisation portal;
- admin operations/B2B finance screens;
- chat and communications;
- E2EE key, direct-chat and group-session logic;
- calling;
- PDF study reader/canvas;
- offline document/material/chat/activity/avatar storage;
- navigation/loading guards;
- study sharing.

## 4. Authentication and session lifecycle

The current User model includes account identity, academic context, profile fields, email verification state, suspension state, activity timestamps, and session_version.

Authenticated HTTP sessions stamp the session version. The runtime compares it with the current account version so password changes or forced invalidation can invalidate stale sessions.

Socket.IO performs the same account/session-version check. Suspended or stale-version accounts cannot establish/use the authenticated realtime connection.

Frontend realtime state has an explicit resetChatRealtime() teardown path used during navigation to login.

## 5. Core data model

The main application defines SQLAlchemy models including:

- User
- University
- Program
- ContentItem
- Payment
- SystemSetting
- ViewProgress
- DocumentContent
- Document
- DocumentReadingProgress
- GeneratedMaterial
- AiJob

Additional chat, E2EE, organisation, billing, and operational tables are represented through the repository's SQL migrations and related modules.

DocumentContent represents deduplicated underlying file content. Its identity is a SHA-256 content hash.

Document is the student's reference to that content and carries student-specific state such as title, filename, status, removal state, reporting state, and last-opened state.

GeneratedMaterial is tied to DocumentContent rather than directly to one student's Document. It stores material type, status, payload, generation fingerprint, generation parameters/version, privacy scope, optional owner, and content-review state.

## 6. AI generation architecture

ai_service.py is the direct provider boundary.

The audited implementation contains:

- openai:gpt-5-mini
- openai:gpt-5.6-luna

Configured task models are checked for the openai: prefix. The Gemini provider implementation was removed during Day 9 so the repository's current provider boundary matches the OpenAI-only product decision.

The task table includes forum answer, thread summary, OCR transcription, tutoring, summarization, flashcards, quizzes, document analysis, podcast script, and mind map.

ai_reusable_generation.py normalizes generation parameters and enforces the current per-generation ceilings:

| Material | Current ceiling |
|---|---:|
| Summary | 10 pages |
| Podcast | 50 minutes |
| Flashcards | 50 cards |
| Mind map | 50 nodes |

Quiz has no entry in GENERATION_MAXIMA in the audited source.

The fingerprint includes source content hash, material type, parameters, prompt version, schema version, and privacy scope/owner where applicable.

The generation path first checks for an exact ready artifact. If found, it does not perform another provider generation and does not create a new AiJob for that reuse path. The student's AI allowance has still been consumed.

For concurrent requests for the same generation family, the database-backed generation store elects a producer and lets other requests wait for the same provider artifact. The implementation contains generation leases/fencing and recovery paths.

## 7. AI economics and plans

ai_economics.py provides default plan configuration and stores active configuration in student_plan_config.

| Plan | Price/month | Podcast | Summary | Questions | Mind map | Flashcards |
|---|---:|---:|---:|---:|---:|---:|
| Free | 0 KES | 10 min | 10 pages | 20 | 30 | 100 |
| Plus | 499 KES | 120 min | 40 pages | 100 | 150 | 300 |
| Pro | 999 KES | 350 min | 100 pages | 210 | 350 | 600 |

All three default configurations currently have offline study and Study Hub uploads enabled. Premium library is enabled only for Plus and Pro.

The repository also tracks Ada-specific daily/monthly usage units and request economics.

## 8. AI background jobs

There are two materially different background-job paths.

### General document AI generation

_start_async_material_generation() in app.py creates an AiJob and starts a daemon Python thread inside the web process.

This is not a durable external queue.

If the web process dies, the database job row can survive while the Python thread disappears. Day 8 added _recover_stale_ai_jobs() so sufficiently old processing jobs are changed to failed and marked safe to retry.

The existing fingerprint/idempotency layer is what makes retrying safe with respect to duplicate provider artifacts.

### Podcast audio

Podcast audio uses a separate database job path.

podcast_audio.py creates a pending AiJob with feature podcast_audio.

kokoro_control.py lets an authenticated standalone worker atomically claim pending jobs with PostgreSQL FOR UPDATE SKIP LOCKED.

The worker identity is stored on the job and required for progress/completion operations.

This is different from the general in-process document-generation thread.

## 9. Podcast/Kokoro implementation

kokoro_worker/worker.py is a FastAPI service.

It:

1. authenticates to the Prepza control plane;
2. claims one pending podcast job;
3. synthesizes each speaker turn using local Kokoro;
4. combines the resulting audio;
5. corrects duration with FFmpeg when within the safe correction range;
6. verifies final duration;
7. uploads MP3 audio to R2;
8. reports completion to the Flask control plane.

The repository defaults the speaker mapping to:

- Lec -> bm_george
- Morio -> am_adam
- Kichwa -> af_sarah

The worker has heartbeat and idle behavior. gpu_autoscaler.py contains lifecycle/scaling policy and records scaling decisions in PostgreSQL.

The repository example environment keeps autoscaling in dry-run/manual mode. Code for autoscaling exists, but that does not mean a GPU provider is currently running or being charged.

## 10. Realtime chat

realtime_server.py is the Socket.IO entrypoint.

PostgreSQL/HTTP persistence remains the source of truth and Socket.IO is the realtime transport.

When REDIS_URL exists:

- Socket.IO uses Redis as its message queue;
- presence state uses Redis;
- persisted E2EE message broadcasts enter the Redis Stream path;
- chat_event_worker.py can consume that stream and emit through Socket.IO.

The Redis Stream implementation has consumer groups, acknowledgement, and stale pending-entry reclamation using XAUTOCLAIM when supported.

When Redis is absent, the code retains a direct single-instance broadcast fallback for relevant message events.

## 11. E2EE boundary

The repository's E2EE documentation defines the current release as single-device per account.

The server stores the account public identity key, while the private identity key remains on the browser/device.

The server must not request, accept, store, or reconstruct a private identity key.

The future multi-device design is explicitly a separate protocol version involving per-device identities and key envelopes. It is not part of the current release implementation.

## 12. Offline architecture

Offline functionality is implemented in separate frontend modules:

- offline/bootstrap.ts
- offline/studyHubOffline.ts
- offline/generatedMaterials.ts
- offline/chatOfflineQueue.ts
- offline/chatMessageCache.ts
- offline/studyActivity.ts
- offline/avatarCache.ts

Account isolation clears relevant local databases/caches when the authenticated account changes.

The repository's offline study-time logic uses the Nairobi calendar boundary and the current 12-hour daily ceiling.

## 13. Storage

object_storage.py is provider-neutral at the application boundary.

When all four R2 variables are configured:

- R2 is enabled;
- logical buckets are represented as prefixes within one physical bucket;
- presigned GET/PUT operations are available;
- object delete/head/read/write operations are available;
- usage telemetry can enumerate objects.

The Flask application still contains Supabase Storage compatibility fallback paths. Therefore the repository currently supports a transition path rather than a completed storage cutover.

## 14. Payments

Payment models and modules use Paystack as the active provider.

Payment records retain user/content association, amount/status, provider, references, payment type, plan, subscription period, and allowance snapshot.

Student subscription entitlement logic validates successful/fulfilled orders and active entitlement periods.

Live Paystack credentials and live webhook/checkout behavior are deployment-time concerns and are not established by repository code alone.

## 15. Email

The application uses AWS SES through boto3 for transactional email paths.

The verification-link path requires BASE_URL.

The old hard-coded Render hostname was removed. The runtime now uses BASE_URL, then RENDER_EXTERNAL_URL as a deployment-provided fallback.

## 16. Security controls visible in the audited source

The application sets:

- X-Frame-Options: DENY
- X-Content-Type-Options: nosniff
- Referrer-Policy: strict-origin-when-cross-origin
- HSTS
- Content-Security-Policy: frame-ancestors 'none'

The code also contains authenticated ownership checks for student documents, privacy-scope checks for generated materials, active-chat-participant checks, session-version checks, Socket.IO authentication, E2EE key lifecycle protections, idempotency handling for relevant message/payment/generation paths, worker authentication for Kokoro control endpoints, and separate worker/control tokens for GPU lifecycle operations.

These are source-level controls; they do not replace live security testing against the deployed environment.

## 17. Database migration model

The repository contains 41 SQL files under migrations/.

There is no Alembic/Flask-Migrate migration framework in the audited repository. The current model is a hand-managed SQL migration collection plus the new checksum ledger.

20261001_migration_history.sql creates schema_migration.

scripts/apply_migrations.py provides:

- explicit baseline;
- ordered apply of unrecorded files;
- checksum verification.

The ledger migration is excluded from being treated as a migration that records itself.

Important: baseline does not prove that an existing database schema is correct. It only records repository migration state. A database must be schema-verified before being baselined.

## 18. Backup tooling

scripts/backup_postgres.py reads DATABASE_URL and uses:

~~~text
pg_dump --format=custom --no-owner --no-acl
~~~

It then runs pg_restore --list against the archive.

--check-only verifies that pg_dump and pg_restore are available without connecting to PostgreSQL.

The repository does not currently provide an external backup destination, retention service, or completed restore drill.

## 19. Deployment artifacts

The repository contains Dockerfile, docker-compose.vps.yml, deploy/vps/README.md, .env.example.vps, REALTIME_DEPLOYMENT.md, Kokoro worker Dockerfile/startup files, and staging load-test workflow/scripts.

The main Docker image builds the frontend first, then packages the Python runtime and frontend distribution into a Python 3.12 image.

The runtime command is:

~~~text
gunicorn -k gthread -w 1 --threads 100 realtime_server:app
~~~

The Dockerfile does not itself create PostgreSQL, Redis, R2, SES, Paystack, OpenAI, or a GPU resource.

## 20. CI and validation surface

The repository contains GitHub workflows for frontend build, student frontend/backend contracts, admin routes, B2B contracts, realtime runtime, E2EE security/chat/envelope validation, AI economics/generation architecture, Kokoro worker validation/image, screen loading, Chat UX, study/navigation flows, Prepza control, and staging load testing.

At the Day 9 checkpoint, the 11 configured launch-contract workflows were all green.

The test/validation tree includes focused tests for AI economics/reuse/artifacts, B2B billing, student orders/subscriptions, document runtime, and chat event queue, plus architecture validators under scripts/ and tools/.

## 21. Current implementation boundaries

| Area | Current repository state |
|---|---|
| React/TypeScript PWA | Implemented |
| Flask application | Implemented |
| PostgreSQL integration | Implemented |
| Socket.IO realtime | Implemented |
| Redis integration | Implemented as an optional configured dependency |
| Redis chat event worker | Implemented as a separate worker |
| E2EE chat | Implemented within the current single-device protocol boundary |
| Offline storage | Implemented |
| OpenAI-only AI provider boundary | Implemented |
| Exact AI artifact reuse | Implemented |
| AI generation-family collapse/leases | Implemented |
| General AI background jobs | Process-local daemon thread + stale-job recovery |
| Kokoro podcast worker | Implemented as separate worker/control path |
| R2 support | Implemented behind provider-neutral helpers |
| Supabase Storage fallback | Still present |
| Paystack integration | Implemented; live provider verification pending |
| SES integration | Implemented; live sender/delivery verification pending |
| GPU autoscaler | Implemented in code; example configuration is dry-run/manual |
| Migration checksum ledger | Implemented |
| PostgreSQL backup archive tooling | Implemented |
| Backup restore drill | Not yet demonstrated |
| Production Render verification | Not yet demonstrated in this repository audit |
| VPS production deployment | Not yet demonstrated |
| Measured production/load capacity | Not yet demonstrated |
| Multi-device E2EE | Future protocol design, not current implementation |

## 22. Operational rules for future work

1. Keep implementation claims tied to source code or a passing repository validation.
2. Do not call infrastructure live because environment variables or scaffolding exist.
3. Do not call a queue durable unless the code actually has an external durable queue/worker boundary.
4. Do not baseline a database until its schema has been independently verified.
5. Do not remove Supabase storage fallback until the R2 path has been tested with real objects.
6. Do not enable GPU autoscaling simply because the autoscaler code exists; the example configuration intentionally keeps it dry-run/manual.
7. Preserve exact artifact reuse, generation fingerprinting, quota accounting, and duplicate-collapse behavior when changing the AI pipeline.
8. Treat CI as contract evidence, not as proof of live provider/database infrastructure.
9. Keep this document factual and update it from the repository when architecture changes.

## 23. Day 10 conclusion

The repository at the audited checkpoint is a substantial integrated application with frontend, backend, database, offline, E2EE, realtime, AI, payments, B2B, storage, email, and Kokoro worker components.

Its implementation is ahead of its live-infrastructure proof.

The remaining work is therefore primarily deployment verification, external-provider verification, backup/restore proof, and measured runtime/capacity evidence, rather than documenting those items as though they already exist in production.
