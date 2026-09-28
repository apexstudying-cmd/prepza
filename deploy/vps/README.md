# Prepza VPS foundation

This is the parallel VPS deployment path. It does not replace the current
Render/Supabase production environment.

## Target foundation

- Ubuntu LTS VPS
- 4 vCPU / 8 GB RAM / about 80 GB NVMe starting point
- Docker + Docker Compose
- PostgreSQL
- Redis
- Prepza Flask HTTP app
- Prepza realtime server
- R2 for persistent object storage/backups
- Vast.ai only for on-demand Kokoro GPU capacity

## Safety rule

Do not point the VPS at the production database yet. The first VPS run should
use a fresh test database or a restored copy. Render/Supabase stays untouched
until CI, restore checks, health checks, realtime checks and load tests pass.

## Process settings

The HTTP container uses gunicorn app:app without adding new worker/thread
settings. The realtime container preserves the existing Prepza command:

gunicorn -k gthread -w 1 --threads 100 realtime_server:app

We will measure before changing these settings.

## Database migration note

The repository deployment path does not currently expose an Alembic migration
workflow. This foundation therefore does not auto-run destructive schema
commands. Before production migration we must build an explicit PostgreSQL
backup/restore and schema migration procedure and verify it against a disposable
database.

## Next steps

1. Create and secure the VPS.
2. Install Docker/Coolify.
3. Put secrets in the VPS environment, never Git.
4. Bring up PostgreSQL/Redis and restore a test database.
5. Build and start Prepza.
6. Add R2 backup jobs and operational health checks.
7. Add admin infrastructure telemetry.
8. Run progressive load tests: 100 -> 500 -> 1,000 -> 2,500 -> 5,000 DAU-equivalent.
9. Only then consider production cutover.
