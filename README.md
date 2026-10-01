# Prepza

Prepza is a Progressive Web App for university students. The current repository contains a React/TypeScript frontend, a Python/Flask application backend, PostgreSQL-backed persistence, Socket.IO realtime chat, offline browser storage, AI study-material generation, B2B/organisation features, Paystack payment flows, and a separate Kokoro GPU worker path for podcast audio.

## Repository status

This documentation was written from the implementation on main at commit b63df1045c6643c0495b53b355873a5c14f986ef and is intended to describe the code that actually exists, not a planned architecture.

The repository's automated CI suite was green on that audit checkpoint. That is not the same as production deployment verification: the Render environment, live provider credentials, live storage migration, backup/restore drill, and real infrastructure capacity still require deployment-time verification.

## Architecture at a glance

~~~text
Student browser
  |
  +--> React / TypeScript PWA
  |      +--> IndexedDB + Cache Storage for offline features
  |      +--> Socket.IO client for realtime chat
  |      +--> browser-side E2EE key/session handling
  |
  +--> Flask application
         +--> PostgreSQL via SQLAlchemy
         +--> AI generation + artifact/reuse/economics layers
         +--> Paystack payment flows
         +--> SES email path
         +--> Supabase Storage compatibility fallback
         +--> R2-compatible object storage path
         +--> Socket.IO realtime server
         +--> Redis integrations when configured
         |
         +--> Kokoro control API
                |
                +--> standalone Kokoro GPU worker
                       +--> Kokoro TTS
                       +--> R2 audio storage
~~~

## Main implementation areas

- app.py — Flask application, SQLAlchemy models, authentication/session handling, document/library flows, payments, AI jobs, and many HTTP routes.
- ai_service.py — provider boundary, task routing, OpenAI calls, token/cost accounting, and AI response handling.
- ai_reusable_generation.py / ai_generation_store.py / ai_artifact_fingerprint.py — reusable generation, artifact identity, leases, in-flight collapse, and exact-match reuse.
- usage_billing.py / ai_economics.py — student AI allowances and economics accounting.
- object_storage.py — provider-neutral R2 helpers with Supabase compatibility paths elsewhere in the application.
- realtime_server.py — Socket.IO entrypoint and realtime authentication/presence.
- chat_event_queue.py / chat_event_worker.py — optional Redis Stream chat-event delivery.
- podcast_audio.py / kokoro_control.py — podcast-audio job creation and authenticated worker control.
- kokoro_worker/ — standalone FastAPI worker that calls local Kokoro, fits audio duration, and uploads completed audio.
- frontend/src/offline/ — offline study, generated material, chat, activity, avatar, and account-isolation code.
- frontend/src/crypto/ — E2EE chat, keys, groups, calls, and secure study/chat components.
- migrations/ — hand-managed SQL migration collection.
- scripts/ and tools/ — audits, validators, migration/backup helpers, build transformations, and architecture checks.
- .github/workflows/ — repository CI and validation workflows.
- Dockerfile / docker-compose.vps.yml / deploy/vps/ — VPS deployment scaffolding.

## Frontend

The frontend lives under frontend/ and uses React 19, TypeScript, Vite 8, Tailwind CSS 4, Socket.IO client, and pnpm 10.34.3.

The package's prebuild intentionally runs a long chain of repository source-transformation and audit scripts before the actual build. The authoritative package build command is:

~~~bash
pnpm run build
~~~

## Backend

The main application is Python 3.12-compatible Flask with Flask-SQLAlchemy, SQLAlchemy, PostgreSQL via psycopg2, Flask-SocketIO, Flask-Limiter, Redis client, boto3, requests, Sentry SDK, PyMuPDF, pydub and ffmpeg-related audio support.

The realtime production command encoded in the Docker image is:

~~~text
gunicorn -k gthread -w 1 --threads 100 realtime_server:app
~~~

## Data and storage

PostgreSQL is the application's primary structured-data store.

The repository has a deduplicated DocumentContent model keyed by SHA-256 content hash, with student-specific Document rows pointing at the underlying content. Generated materials are associated with the underlying document content so reusable artifacts can be shared according to their privacy/publication scope.

Large/private objects use logical storage buckets. object_storage.py provides an R2-compatible S3 API path; application code also contains Supabase Storage compatibility fallback paths.

## AI generation

The current provider boundary is OpenAI-only. The code contains OpenAI model identifiers for openai:gpt-5-mini and openai:gpt-5.6-luna.

Configured task models are guarded so a non-openai: provider is rejected.

Document generation supports the repository's current material types: summary, quiz, flashcards, podcast script, and mind map.

Generation uses normalized parameters, content hash, material type, prompt/schema versions, privacy scope, generation fingerprint, quota accounting, exact ready-artifact lookup, in-flight generation-family collapse, lease/fencing/recovery mechanisms, and provider generation only when a reusable artifact is unavailable.

Exact artifact reuse still consumes the student's allowance; it avoids a new provider generation.

Per-generation ceilings currently encoded in ai_reusable_generation.py are 10 summary pages, 50 podcast minutes, 50 flashcards, and 50 mind-map nodes. Quiz has no entry in that maxima table.

## Student plans

The default plan configuration in ai_economics.py contains Free, Plus, and Pro monthly plans.

| Plan | Price | Podcast min | Summary pages | Questions | Mind-map nodes | Flashcards |
|---|---:|---:|---:|---:|---:|---:|
| Free | KES 0 | 10 | 10 | 20 | 30 | 100 |
| Plus | KES 499/month | 120 | 40 | 100 | 150 | 300 |
| Pro | KES 999/month | 350 | 100 | 210 | 350 | 600 |

Offline study and Study Hub uploads are enabled in the current default configuration for all three plans. Premium library is disabled for Free and enabled for Plus/Pro.

## Realtime and E2EE

HTTP/database persistence remains the source of truth for chat. Socket.IO provides low-latency realtime transport.

When Redis is configured, the realtime server uses Redis for Socket.IO message-queue fan-out, presence state, and the dedicated chat event stream. Without Redis, the code retains a single-instance direct Socket.IO fallback for message broadcasts.

Socket authentication checks the signed-in user, suspension state, and account session_version. Frontend logout/navigation teardown can reset the realtime singleton.

The current E2EE architecture is explicitly single-device per account. The private identity key remains on the browser/device and is not uploaded to the server. Multi-device E2EE is documented as a future protocol version rather than silently changing the current key semantics.

## Podcast audio

Podcast script generation is handled by the AI pipeline. Audio generation is a separate Kokoro worker path.

The Flask control plane creates a durable AiJob with feature podcast_audio. A standalone worker claims pending podcast jobs with PostgreSQL row locking, calls local Kokoro once per speaker turn, uses FFmpeg/pydub for duration correction, verifies the final duration, and uploads the resulting MP3 to R2.

The repository currently maps podcast speakers through environment-configured voices, with defaults for Lec, Morio, and Kichwa.

The optional GPU autoscaler contains explicit price, worker, queue, resource, and provider-credit safety ceilings. The repository's example VPS configuration keeps autoscaling in dry-run/manual mode.

## Offline architecture

The frontend has separate offline modules for study documents, generated materials/audio, chat, study activity, avatars, and account isolation.

Offline account isolation clears the relevant local databases/caches when the authenticated account changes so one account's local study/chat material is not reused by another account.

Study activity synchronization uses the repository's Nairobi date-boundary rules and the current 12-hour daily study ceiling.

## Payments and B2B

The application contains Paystack payment/subscription flows and separate B2B organisation/campaign accounting modules. Payment records retain provider/reference information and subscription entitlement periods.

Live payment-provider verification remains a deployment task; repository tests do not prove a live Paystack account configuration.

## Email and monitoring

The application has an SES path for transactional email and a Sentry integration.

Verification links require a configured BASE_URL; the repository no longer relies on the previously hard-coded Render URL.

Live SES sender verification and delivery still require real environment verification.

## Database migrations and backups

There are currently 41 SQL files under migrations/. They form a historical, hand-managed migration collection rather than an Alembic/Flask-Migrate system.

scripts/apply_migrations.py provides a checksum ledger for future migration tracking:

- --baseline records known migration checksums without applying their SQL.
- --apply applies unrecorded migrations and records their checksums.
- --verify checks the ledger against repository migration files.

The ledger definition itself is excluded from the migration set so it cannot record itself.

scripts/backup_postgres.py can create a PostgreSQL custom-format dump and verify it with pg_restore --list. Its --check-only mode only checks local PostgreSQL backup tooling and does not connect to a database.

A real production backup destination, retention policy, encryption policy, and restore rehearsal are still operational requirements.

## Deployment boundary

The repository contains Docker/VPS deployment scaffolding and a realtime Gunicorn command. It does not prove that a production deployment is currently running.

The documented environment example includes PostgreSQL, Redis, SES, OpenAI, Paystack, Google OAuth, Sentry, R2, Kokoro worker/control, and optional Vast autoscaling variables.

No infrastructure resource is created merely by having those variables or code in the repository.

## CI

The repository contains workflows covering frontend build, student contracts, admin routes, B2B contracts, realtime runtime, E2EE security/chat, AI generation/economics, screen loading, Chat UX, Kokoro worker validation, navigation/study flows, and staging-load-test scaffolding.

At the Day 9 checkpoint, the configured 11-workflow launch-contract family passed on the audited main commit.

## Further technical reference

See:

- docs/DAY10_TECHNICAL_DOCUMENTATION.md
- docs/DAY8_RUNTIME_READINESS.md
- docs/LAUNCH_READINESS.md
- docs/e2ee-multidevice-architecture.md
- docs/e2ee-study-chat-rollout.md
- docs/study-chat-ux-contract.md
- docs/ADMIN_ROUTE_CONTRACT.md
