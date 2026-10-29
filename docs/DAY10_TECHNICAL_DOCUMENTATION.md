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

---

## Addendum — RAG, embeddings, grounded tutoring, and Morio identity
**Reviewed against GitHub main on 2026-10-29.** This addendum is a newer source review, not a rewrite of the historical 2026-10-01 checkpoint above. The dated sections above describe the audited source checkpoint stated at the top; use this addendum and the current verified system walkthrough for the later findings.

### 15. How an AI answers from a student's notes

An LLM does not automatically see a student's files or remember every uploaded note. The application must deliberately provide the relevant text or retrieve it from an authorized knowledge store. The model then generates an answer using the instructions and context included in that request.

The current E2EE scoped-study route in `e2ee_ada_routes.py` demonstrates **explicit in-context grounding**:
1. The student deliberately selects study text/pages and asks a question.
2. The browser sends the selected text, page range, question, document/attachment reference, and encryption key epoch to the route.
3. The server checks the signed-in user, active conversation membership, selected-context declaration, document ownership/share status, page range, and current E2EE key epoch.
4. The selected text and question are placed directly into the model request. The system instruction says to use the supplied context plus general academic knowledge, not claim access to other private data, and acknowledge when the excerpt is insufficient.
5. The model response is returned to the student and usage is logged.

This is useful grounding, but it is **not a general-purpose RAG pipeline**: the route does not search a corpus of note chunks or query an embedding/vector index. It sends the explicitly selected excerpt. It also intentionally does not read encrypted chat history or decrypt messages on the server.

Document-material generation has a separate pipeline: source document content is used to generate structured summaries, quizzes, flashcards, mind maps, or podcast scripts; matching completed artifacts can be reused. This should not be described as semantic RAG unless a retrieval stage is actually implemented and tested.

### 16. RAG and embeddings — terms and implementation status

- **RAG (Retrieval-Augmented Generation):** retrieve relevant source passages first, then add those passages to the model input so the response can be grounded in the right source material.
- **Chunking:** divide a long PDF/lecture note into manageable, overlapping or section-aware passages, preserving metadata such as document, course, page, heading, and owner.
- **Embedding:** use an embedding model to turn text into a numerical vector that represents semantic relationships. Similar ideas can have nearby vectors even when they use different words.
- **Vector index/database:** store chunk vectors and metadata so the system can retrieve likely-relevant passages efficiently.
- **Keyword/full-text search:** find exact terms and lexical matches. This is useful and complementary to embeddings; it is not the same thing as embeddings.
- **Reranking:** score a shortlist of candidate passages more carefully so the most useful evidence is placed in the prompt.
- **Grounding/citations:** keep source/page metadata with retrieved passages, instruct the model to answer from evidence, and show students which note/page supports the answer.
- **Prompt/system instruction:** application-controlled guidance about the assistant's role, identity, boundaries, and response style. It steers the model but is not a security boundary by itself.
- **Conversation/learning memory:** separately stored, permissioned information about prior questions, progress, preferences, misconceptions, and mastery. This is not the same as RAG over course notes and should be designed with explicit privacy and retention rules.

**Current implementation:** the reusable forum-answer cache in `ai_service.py` still uses PostgreSQL full-text search (`tsvector`) and `pg_trgm`; it is not embeddings-based RAG. The new `study_retrieval.py` provides page-aware chunking, lexical ranking, optional injected embedding callbacks, and citation envelopes. `document_pipeline.py` now persists extracted page text in `document_page_text`, alongside the existing combined `extracted_text` field for backward compatibility. Each page row stores the content hash, extractor version, and a document-wide source version.

The new `study_retrieval_service.py` loads page rows through a SQL query that enforces access before text is returned: the requester must own a non-removed, ready document or its exact document must have an approved Library publication matching the requester's university, program, year, and semester. A shared content hash alone grants no access. `POST /api/study/retrieval` requires an authenticated session and CSRF token, takes the user ID from the session, supports optional server-authorized document scope, and returns source/page citations. The ordinary Morio document tutor now passes its selected document ID from the authenticated route, loads only authorized page rows, ranks passages for the current question, and adds the bounded results in a separate system-message block. The prompt instructs Morio to say when retrieved pages do not establish an answer; a post-generation validator downgrades page numbers that were not among the retrieved pages. It currently uses lexical retrieval only, with hard caps of 250 authorized page rows, 20,000 characters per page materialized for ranking, and 500 chunks per request to bound database/memory work; no production embedding vectors are stored and no paid embedding API is called. The scoped E2EE tutor remains separate and continues to use only explicitly selected context.

**Version invalidation:** when re-extraction changes page text, ready generated materials for that content are marked failed with an explicit regeneration message so they are not silently served as current. First-time page-text backfills that match existing combined text do not invalidate artifacts. Retrieval citation versions are content-addressed from the uploaded content hash, extractor version, page numbers, and extracted page text.

Existing ready PDFs are not silently or automatically re-OCRed after migration. `scripts/backfill_document_page_text.py` defaults to a read-only inventory; its explicit `--apply` mode only backfills documents where every page has sufficient native PDF text. Scanned/mixed PDFs are skipped rather than invoking billable OCR. Rehearse the script on a disposable/staging database and review counts before applying it to production.

### 17. Current retrieval flow and remaining production gates

The first lexical, page-cited phase is now implemented in the ordinary Morio document tutor. The runtime flow is:

```text
Student asks Morio a question
        |
        v
Authenticate + authorize the student's course/documents
        |
        v
Detect scope (selected excerpt, current document, course notes,
or explicitly shared E2EE material)
        |
        v
Retrieve authorized page chunks (lexical ranking; embedding adapter remains optional)
        |
        v
Apply owner/cohort permissions in SQL before reading page text; rank and deduplicate
        |
        v
Build a bounded prompt with source/page metadata
        |
        v
Generate answer using the configured model
        |
        v
Validate page numbers against retrieved evidence; return explanation + citations + uncertainty when evidence is weak
        |
        v
Log usage and quality signals without leaking private note content
```

Remaining engineering gates before broad production enablement:
- Apply the additive SQL migrations through the controlled migration process and rehearse the page-text backfill on staging; existing ready documents are not silently re-OCRed.
- Preserve strict per-user, course, and sharing boundaries in every retrieval query; never let one student's private notes appear in another student's context.
- Keep the E2EE boundary intact. Server-side indexing of encrypted private messages/documents must not silently bypass the protocol. For E2EE chats, only explicitly selected context should be sent to the AI operation, with clear consent and scope.
- Store source metadata and chunk/version identifiers so citations remain traceable after a document is updated or removed.
- Use hybrid retrieval (keyword plus embeddings) rather than assuming embeddings alone will find exact formulae, course codes, names, or numeric facts.
- Add evaluations for retrieval recall, answer correctness, citation correctness, insufficient-context behavior, access-control isolation, prompt injection in uploaded notes, latency, and cost.
- Keep RAG optional for small/selected excerpts where direct context is simpler and more reliable. Do not add a vector database until an evaluation demonstrates that it improves retrieval quality enough to justify operational complexity.

### 18. Assistant identity: requested change from Ada to Morio

The product direction requested on 2026-10-29 is for the student-facing AI tutor to identify itself as **Morio**, not Ada or ChatGPT. This is a product identity/prompt/UI change, not a change of underlying model provider.

**Implementation update (2026-10-29):** the primary document tutor prompt in `ai_service.py` and the explicitly scoped E2EE study prompt now identify the student-facing tutor as Morio. The Home quick action, document-study labels, chat composer mention (`@Morio`), shared/direct study panels, loading/error copy, and responsive-browser acceptance check have been updated to Morio. Internal module, function, and endpoint names that contain `Ada` remain for compatibility; they are not intended as user-visible identity. The responsive/offline/cross-system browser regression passed on runtime commit `fe8bbbb195d2090c481052172b8af5ec9176e9bc` in [run 40856781684](https://github.com/apexstudying-cmd/prepza/actions/runs/40856781684), including phone/tablet checks, the full disposable PostgreSQL QA suite, and online/offline generated-material journeys. The podcast character named Morio is a separate feature and its voice mapping does not prove the tutor implementation.

Recommended migration: define one canonical display identity (“Morio”) and a small set of central prompt constants; update student-visible tutor introductions and UI labels, then route/telemetry copy and tests. Avoid blindly renaming internal route/module names in the same change because they are compatibility contracts and may be used by the frontend or existing tests. Add regression tests asserting that the student-facing tutor introduces itself as Morio and does not self-identify as Ada or ChatGPT, while preserving provider/model transparency where technically or legally appropriate. Test the ordinary tutor, E2EE scoped tutor, errors/empty states, and podcast character labels separately.

### 19. Learning resources

- Google Cloud Tech — [Build RAG apps with embeddings (YouTube)](https://www.youtube.com/watch?v=A7qjjkjjZu0): embeddings, chunking, vector search, and production considerations.
- 3Blue1Brown — [Large Language Models explained briefly (YouTube)](https://www.youtube.com/watch?v=LPZh9BOjkQs): beginner-friendly model and chatbot foundations.
- Anthropic — [Retrieval augmented generation guide](https://platform.claude.com/cookbook/capabilities-retrieval-augmented-generation-guide): hands-on chunking, embeddings, retrieval, and reranking.
- Anthropic — [Contextual Retrieval](https://www.anthropic.com/research/contextual-retrieval): why chunk context and hybrid keyword/semantic search matter.
- Anthropic — [Prompting best practices](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/prompt-templates-and-variables): role/system prompts, examples, structured context, and identity instructions.
- OpenAI — [Prompt engineering guide](https://developers.openai.com/api/docs/guides/prompt-engineering): provider-neutral concepts for giving a model relevant context and constraining its response.

### 20. Work remaining for this AI area

1. Implement and regression-test the requested Morio identity across student-facing tutor prompts and UI.
2. Map each tutoring entry point to its actual source context and explicitly document whether it uses selected text, whole-document text, cached answers, or retrieval.
3. Design a privacy-aware hybrid RAG prototype for non-E2EE study notes, with chunk/page citations and an evaluation set, before choosing a vector store.
4. Keep RAG/embedding work separate from the remaining release gates for Paystack, SES, OpenAI, R2, and the configured Kokoro/GPU provider. External-provider verification still requires safe credentials and explicit approval for any potentially billable or live operation.


---

## 21. System prompts, MCP tools, access control, guardrails, routing, caching, and observability

These are separate layers of an AI application. They complement RAG; none is a substitute for source retrieval or access-control enforcement.

### System prompt
Application-controlled instructions define the assistant's role, teaching style, evidence policy, and output format. The primary document tutor and scoped E2EE study tutor now say Morio. Prompts are guidance, not a security boundary: the backend must still enforce access, quotas, tool permissions, and data scope.

### Tools and MCP
A model tool is a narrowly defined function that the application can execute on the model's behalf, such as looking up an authorized course topic or retrieving a note passage. **MCP (Model Context Protocol)** is a standard way for an AI application to connect to external tools and data sources; it is not itself an LLM, embedding model, or RAG database.

**Current status:** this source review did not verify an MCP-connected tool server for Morio. Prepza has application routes and internal functions, but do not describe those as MCP tools. If we add tools, use an explicit allowlist, JSON-schema validation, per-user authorization at execution time, timeouts, rate limits, audit events, and human confirmation for consequential actions. Tool output is untrusted input and must not be allowed to override system instructions.

### Access and privacy
Existing boundaries include authenticated sessions, document access checks, CSRF on mutations, chat membership checks, explicit selection for the E2EE tutor, bounded text/page ranges, and E2EE key-epoch validation. For future RAG, enforce the same owner/course/share constraints *before* passages reach the model. A prompt saying “do not reveal another student's notes” is not an adequate authorization control.

Do not silently index server-inaccessible E2EE plaintext. Preserve the current explicit-selection disclosure model for encrypted chats unless a separately reviewed design changes it with informed consent.

### Guardrails
Prepza already has spend caps, daily tutor limits, route-level rate limits, bounded selected context, provider error handling, and structured output contracts for some generation types. These protect cost and some malformed inputs. They do not eliminate hallucinations, prompt injection, unsafe tool arguments, or incorrect citations. Future RAG needs tests for cross-user isolation, malicious instructions inside uploaded notes, insufficient evidence, unsupported claims, citation correctness, and output validation.

### Cache and router
- `route_and_generate()` routes by AI task, selects the configured primary model, and can try a configured fallback after provider failure. It currently uses the OpenAI-only provider policy; quality-based escalation is documented as future work.
- `AIRequest.cacheable_system` enables provider prompt-cache behavior where supported. This is distinct from caching a final answer.
- Study artifact fingerprints and exact artifact reuse avoid repeating equivalent summary/quiz/flashcard/mind-map/podcast generations. The forum-answer reuse cache uses PostgreSQL text/similarity search; it is not embeddings-based note RAG.
- A future RAG retrieval cache must be keyed by authorized user/scope, document version, query/embedding version, and relevant permission state; it must be invalidated when source documents or access rights change.

### Observability
The AI routing boundary now emits a random per-request trace ID in its internal response and structured JSON log events for successful calls, failed attempts, fallback use, token/cache usage, estimated cost, model/provider, and latency. Failure logs include the exception type but intentionally omit exception messages. The trace ID is included in the terminal provider error so support can correlate a failure without logging prompts or answers. The contract tests use fake providers and assert that prompt, user-message, completion, and provider exception text do not appear in logs.

The HTTP layer generates a server-owned opaque `X-Request-ID`, adds it to the response, and emits structured request logs using only route template, method, status, latency, and request ID (never query strings, bodies, cookies, IP addresses, or user IDs). Generic `ai_service.route_and_generate` calls and the ordinary Morio tutor now correlate success/failure/citation-validation events with that HTTP request ID. Tutor telemetry includes model/provider, prompt version, latency, token/cache/cost metrics, retrieved-page count, and invalid-citation count, but never the prompt, user message, answer, or provider exception text. Slow requests (5 seconds or more) and HTTP 5xx responses are written to `request_observability_event` using an independent database transaction; records are pruned after 14 days. `GET /admin/observability` exposes the protected data API, rendered as an HTTP observability panel in Admin Operations. It shows recent slow/error events and threshold signals: at least five 5xx responses or ten slow requests in five minutes. These signals are structured warning logs suitable for log-based alerting, not outbound email/page notifications; external log/alert delivery still requires operator configuration. Browser trace propagation and provider request IDs remain future work. The AI economics/retrieval/observability workflow passed 76 tests on commit [275cb521](https://github.com/apexstudying-cmd/prepza/actions/runs/40872652305). The SQL migration remains unapplied outside disposable CI, and the current full browser journey is still running.

### Implementation order
1. [x] Complete Morio identity and responsive/offline browser regression on runtime commit `fe8bbbb195d2090c481052172b8af5ec9176e9bc`.
2. Keep the current direct-document tutoring flow working; distinguish it from semantic RAG in product copy and QA.
3. [~] Add and verify privacy-safe request tracing and structured AI routing telemetry; next add HTTP/job correlation and prompt/schema version metadata.
4. Build a small hybrid-retrieval prototype for non-E2EE notes with page citations and strict access tests; use mocked embeddings in CI and do not make billable embedding calls without approval.
5. Add MCP tools only when a concrete student workflow benefits from them and after permission/audit contracts are tested.
