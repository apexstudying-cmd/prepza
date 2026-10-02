# Database migrations

Prepza now uses **Alembic** for all new schema migrations. Alembic is the SQLAlchemy migration tool and keeps a revision graph for future database changes.

## Baseline

`schema/local_baseline.sql` is a schema-only snapshot reconstructed from the live Supabase `public` schema on 2026-10-02. It contains no production rows. Production RLS/auth/storage policy configuration is intentionally not copied into local PostgreSQL.

## Fresh local database

With PostgreSQL running and `DATABASE_URL` pointing at the disposable local database:

    alembic upgrade head

This creates the verified baseline and records the Alembic revision.

## Existing database

Do **not** run the baseline against an existing database. After independently verifying that its schema matches the baseline:

    alembic stamp 20261002_baseline

This records the starting point without executing the baseline SQL.

## Future schema changes

After changing SQLAlchemy models or a SQL-only schema contract:

    alembic revision --autogenerate -m "describe the schema change"

Review the generated revision before applying it:

    alembic upgrade head

Autogenerate is a candidate generator, not an approval mechanism. SQL-only objects such as some triggers/functions still require explicit migration code.

## Legacy migrations

The existing `migrations/*.sql` collection is retained as historical migration material. It is not replayed to bootstrap a fresh database and new migrations should not be added there.
