# Day 8 — runtime and migration readiness

## Background AI jobs
Prepza records AI jobs in PostgreSQL but currently starts the worker in the web process. If Gunicorn/Render kills that process, the database row survives but the Python thread does not.

The app now detects processing jobs older than AI_JOB_STALE_AFTER_SECONDS (default 3600 seconds) when a new generation starts or job status is checked. Those jobs are marked failed, retry_count is incremented, and the message explains that retry is safe. The existing generation fingerprint/idempotency path remains responsible for preventing duplicate artifacts when a student retries.

This is a recovery guard, not a durable queue. A future Redis/worker deployment can replace the process-local thread without changing the AiJob bookkeeping shape.

## Migration model
The repository contains a historical collection of hand-managed SQL migrations. 20261001_migration_history.sql adds a ledger for future tracking. scripts/apply_migrations.py supports baseline, apply, and verify operations.

Do not run baseline against an unknown database. It records state without changing the schema.

## Backups
scripts/backup_postgres.py creates a PostgreSQL custom-format dump and immediately runs pg_restore --list to verify that the archive is readable. Its --check-only mode validates that pg_dump and pg_restore are available without connecting to a database. It does not upload or schedule anything. A real production backup policy still needs an external destination, retention, encryption, and a tested restore drill.

## Day 8 verification
The final Day 8 main commit passed all 11 configured CI workflows, including frontend build, realtime runtime, E2EE security, AI economics, B2B/student contracts, admin routes, screen loading, Chat UX, and Kokoro worker validation.

## No infrastructure changes
Day 8 does not create Redis, R2, a VPS, a GPU, a Render cron service, or any paid resource.
