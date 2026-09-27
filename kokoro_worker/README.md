# Prepza Kokoro GPU Worker

Standalone GPU worker for Prepza podcast audio generation.

## Runtime contract

- One worker process owns one Kokoro model instance.
- One podcast job is processed at a time.
- Additional jobs remain queued in Prepza's PostgreSQL-backed AiJob queue.
- The worker never connects directly to Prepza's database.
- The worker receives a claimed job over an authenticated internal HTTP request.
- Generated audio is uploaded directly to the configured object store (R2).
- Completion/progress is reported back to Prepza over authenticated HTTP.
- There is intentionally no Render TTS fallback.

The production target is an NVIDIA RTX A2000 6 GB-class worker. The worker image uses the pinned upstream Kokoro-FastAPI GPU image as its inference engine. The upstream project documents NVIDIA GPU support and synchronous inference; its configuration defaults to one worker process, and additional processes load additional model copies.

## Environment

Required:

- `PREPZA_INTERNAL_BASE_URL`
- `PREPZA_INTERNAL_TOKEN`
- `R2_ENDPOINT_URL`
- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`
- `R2_BUCKET` (normally `podcast-audio`)

Optional:

- `POLL_SECONDS` (default 2)
- `KOKORO_LOCAL_URL` (default http://127.0.0.1:8880)
- `KOKORO_MODEL` (default kokoro)
- `KOKORO_TIMEOUT_SECONDS` (default 120)
- `WORKER_HEALTH_PORT` (default 8080)

The worker image starts the upstream Kokoro API on localhost and the Prepza polling worker in the same container. Only the worker health port needs to be exposed.

## Safety

Do not put student session cookies, passwords, OTPs, or database credentials into this worker. It only needs the internal worker token and R2 write credentials.
