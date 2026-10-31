# Local Supabase Data Migration — Engineering Walkthrough

**Status:** In progress — source export and initial schema inventory verified; destination migration and data import are not yet approved or performed.  
**Working branch at investigation start:** `main`  
**Repository commit observed locally:** `49310553`  
**Last evidence update:** 2026-10-31

This is the durable, evidence-based learning record for moving the old Supabase application's data into the current local Prepza database **without replacing the newer local schema**. It also explains the database, frontend/backend, GitHub, Docker, and hosting concepts encountered during the exercise.

> **Safety boundary:** the Supabase database is a read-only source for this exercise. Do not run migrations, restores, deletes, or schema changes against the live Supabase project. Do not restore the entire Supabase archive into the local database. Never put passwords, connection strings, password hashes, tokens, private messages, or personal records in this document.

## 1. Goal and intended outcome

The local Prepza environment contains a newer application schema, while the older Supabase project contains real application data and an existing verified account. The goal is to:

1. Preserve a recoverable backup of the current local database.
2. Export the Supabase database without modifying it.
3. Compare source and destination schemas before importing anything.
4. Bring across only compatible application data, retaining the current local schema and newer local-only tables.
5. Verify row counts, relationships, sequences, and application behavior.
6. Test local login with an existing account, without depending on SES signup email delivery.
7. Record the exact procedure and evidence so it can be repeated safely.

**Not yet completed:** data import, local login verification, post-import application checks, and final restore/rollback rehearsal.

## 2. Progress and verified evidence

| Item | Evidence / result | Status |
|---|---|---|
| Local pre-change backup | `prepza-local-before-reset.dump`, approximately 471 KB | Verified created |
| Supabase source export | `../prepza-supabase-source.dump`, approximately 828 KB | Verified created |
| Archive integrity | `pg_restore --list` exited with code 0 | Passed |
| Supabase archive metadata | Custom format; PostgreSQL source 17.6; 1,402 TOC entries | Inspected |
| Local public table inventory | 112 tables | Counted |
| Supabase public table inventory | 107 tables | Counted |
| Tables only in local inventory | `alembic_version` and four opportunity-target tables | Identified |
| Tables only in Supabase inventory | None found by the table-name comparison | Identified |
| Local schema comparison | Differences found; detailed column/constraint/sequence reconciliation remains | In progress |
| Updated app image | Built successfully from local repository commit `49310553` | Passed |
| Alembic code head | `20261030_shared_study_streak` | Verified in fresh image |
| Local DB Alembic revision | `20261007_doc_material` | Verified |
| Supabase data import | Not run | Pending |
| Local login with imported account | Not run | Pending |

The archive contains Supabase-managed schemas including `auth`, `extensions`, `graphql`, `graphql_public`, `pgbouncer`, `realtime`, `storage`, `supabase_migrations`, and `vault`, as well as `public`. This is why a whole-archive restore is inappropriate for the local application database.

The public-table inventory found these five tables only in the local schema:
- `alembic_version`
- `opportunity_program_target`
- `opportunity_semester_target`
- `opportunity_university_target`
- `opportunity_year_target`

No table names were found only in the Supabase public inventory. This is a **table-name comparison only**; it does not prove that matching tables have identical columns, defaults, indexes, constraints, or data compatibility.

## 3. What PostgreSQL, a dump, and a restore mean

PostgreSQL is the relational database engine used by Prepza. It stores structured records in tables, connects related records using keys, and enforces constraints such as uniqueness and foreign keys.

A database dump is an export of database objects and/or their data. A PostgreSQL custom-format dump:
- is a portable archive rather than a plain SQL script;
- can be inspected with `pg_restore --list`;
- can be selectively restored by schema, table, or data/schema sections;
- supports a controlled restore plan rather than requiring an all-or-nothing SQL replay.

A dump is not automatically safe to restore into any database. The source and destination may have different schema versions, extensions, ownership, sequences, and managed-service objects. The restore plan must match the destination.

### Why we made two backups/exports

The local backup is a recovery point in case an import or local migration damages the destination. The Supabase dump is the source snapshot used for analysis and selective data transfer. They serve different purposes and must be retained separately until the exercise is complete.

## 4. Exact commands used and what they taught us

Run these from the repository directory `~/prepza`, with Docker Desktop running.

### 4.1 Back up the existing local database

```bash
docker compose -f docker-compose.vps.yml exec -T postgres pg_dump -U prepza -d prepza -Fc > prepza-local-before-reset.dump
```

- `docker compose ... exec` runs a command inside the running PostgreSQL container.
- `-T` disables pseudo-terminal allocation, which is useful for piping binary dump output.
- `pg_dump` exports a PostgreSQL database.
- `-U prepza` selects the database role.
- `-d prepza` selects the database.
- `-Fc` requests PostgreSQL's custom archive format.
- `>` redirects the binary output to a file on the Windows/Git Bash host, not inside the container.

The resulting local file was approximately 471 KB. Keep it until the import and verification are complete.

### 4.2 Export the Supabase database without changing it

The direct database hostname did not resolve from the Docker environment. The Supabase Session Pooler hostname from the project's connection settings was used instead. The database password was reset through Supabase after an initial authentication failure. The successful export used environment variables so the password did not need to be written literally into the command history:

```bash
docker compose -f docker-compose.vps.yml exec -T \
  -e "PGPASSWORD=$SUPABASE_DB_PASSWORD" \
  -e "PGSSLMODE=require" \
  postgres pg_dump \
  --format=custom \
  --no-owner \
  --no-acl \
  --host="$SUPABASE_DB_HOST" \
  --port="$SUPABASE_DB_PORT" \
  --username="$SUPABASE_DB_USER" \
  --dbname="$SUPABASE_DB_NAME" \
  > ../prepza-supabase-source.dump.partial
```

After the command completed successfully, the partial file was renamed to `../prepza-supabase-source.dump` and the password variable was unset.

Important options:
- `PGPASSWORD` supplies the password to the PostgreSQL client process. Do not print it or commit it.
- `PGSSLMODE=require` requires TLS for the remote database connection.
- `--format=custom` creates a selective-restore archive.
- `--no-owner` avoids trying to recreate source ownership identities during a restore.
- `--no-acl` excludes source grants/privileges that may not apply locally.
- The temporary `.partial` output prevents a failed/incomplete export from being mistaken for the final archive.

The export completed and the resulting file was approximately 828 KB. No write operation was performed against Supabase.

### 4.3 Verify the archive before relying on it

```bash
docker compose -f docker-compose.vps.yml exec -T postgres \
  pg_restore --list < ../prepza-supabase-source.dump > /dev/null
echo "Archive check exit code: $?"
```

The exit code was `0`. This establishes that PostgreSQL can read the archive's table of contents. It does **not** prove every row can be restored into the destination schema.

### 4.4 Extract only the public schema definition for comparison

The first attempt omitted both `-f` and `-d`:

```bash
pg_restore --schema=public --schema-only --no-owner --no-acl < ../prepza-supabase-source.dump > ../prepza-supabase-public-schema.sql
```

It failed with the message that one of `-d/--dbname` and `-f/--file` must be specified. This was a command-line usage error, not evidence that the archive was corrupt.

The corrected command explicitly directs the SQL output to standard output:

```bash
docker compose -f docker-compose.vps.yml exec -T postgres \
  pg_restore --schema=public --schema-only --no-owner --no-acl \
  -f /dev/stdout \
  < ../prepza-supabase-source.dump \
  > ../prepza-supabase-public-schema.sql
```

The local schema was also exported to `../prepza-local-schema.sql`. The resulting schema files were approximately 204 KB (Supabase public) and 182 KB (local).

### 4.5 Compare table names

```bash
grep '^CREATE TABLE ' ../prepza-local-schema.sql \
  | sed 's/^CREATE TABLE public\.//; s/ .*//' \
  | sort > ../prepza-local-tables.txt

grep '^CREATE TABLE ' ../prepza-supabase-public-schema.sql \
  | sed 's/^CREATE TABLE public\.//; s/ .*//' \
  | sort > ../prepza-supabase-tables.txt
```

The comparison reported 112 local tables and 107 Supabase public tables. A table-name comparison is a useful first inventory, but the next stage must compare columns, types, nullability, defaults, primary/foreign keys, unique constraints, indexes, and sequence behavior.

Raw SQL text diffs also contain irrelevant differences such as PostgreSQL dump-version headers, comments, object ordering, and formatting. A meaningful schema reconciliation compares database objects and their definitions rather than assuming every textual diff is a structural difference.

## 5. Alembic: database schema version control

Alembic is the database migration tool used with SQLAlchemy in Prepza. It is similar in purpose to Git, but it versions database structure rather than application source code.

- **Git commit:** records a version of application files.
- **Alembic revision:** records a database schema change.
- **Migration file:** Python code describing how to move the schema forward (`upgrade`) and, where safe, backward (`downgrade`).
- **Revision ID:** the identifier Alembic stores in the database's `alembic_version` table.
- **down_revision:** the parent revision; it links revisions into a migration history.
- **alembic_version:** a small bookkeeping table recording the currently applied revision. It is not a copy of the schema.

Common commands:
- `python -m alembic heads`: shows the latest revision(s) available in the code.
- `python -m alembic current`: shows the revision recorded by the connected database.
- `python -m alembic history`: displays the migration history.
- `python -m alembic upgrade head`: applies pending migrations up to the latest head. **This changes the connected database and must only be run after review and backup.**
- `python -m alembic downgrade <revision>`: attempts to move backward; it is only safe if the downgrade operations preserve required data.

### 5.1 A filename is not the revision ID

The database reports `20261007_doc_material`. There is no file named exactly `20261007_doc_material.py`, but the file `20261007_document_content_material_link.py` declares:

```python
revision = "20261007_doc_material"
down_revision = "20261005_chat_attach_source_doc"
```

Alembic uses the `revision` variable, not the Python filename. The revision was therefore present; the earlier assumption that it was missing was incorrect.

### 5.2 Migration chain verified from the repository

```text
20261002_baseline
  -> 20261002_user_model
  -> 20261003_opportunity_targeting
  -> 20261004_ai_job_reconcile
  -> 20261005_chat_attach_source_doc
  -> 20261007_doc_material
  -> 20261027_shop_marketplace
  -> 20261028_shop_listing_expiry
  -> 20261029_shop_period_payment
  -> 20261030_shared_study_streak
```

The local database currently records `20261007_doc_material`. The newly built application image reports `20261030_shared_study_streak` as its head. Thus four later revisions are pending in the local database:
1. `20261027_shop_marketplace`
2. `20261028_shop_listing_expiry`
3. `20261029_shop_period_payment`
4. `20261030_shared_study_streak`

This is not by itself a failure. It means the database is at an earlier point in the code's migration history. Before applying those migrations, inspect their operations and compare the actual local schema and imported data with their assumptions.

The October 30 migration creates `study_friend_streak` and `study_friend_streak_activity` with `CREATE TABLE IF NOT EXISTS`. Its downgrade intentionally does nothing because those tables may predate the migration or contain user data. This is a deliberate data-preservation choice, but it also means downgrade does not reverse the table creation.

### 5.3 How Alembic connects to the database in Prepza

The repository's `alembic/env.py`:
- loads `.env` from the repository root;
- requires `DATABASE_URL`;
- creates a SQLAlchemy engine;
- checks whether `public.user` exists;
- imports the application's `db.metadata` if that table exists;
- configures Alembic for online or offline migration execution.

This is important because an Alembic command acts on whichever database the configured `DATABASE_URL` points to. Always verify the target before running a migration. A command run with production credentials can change production even if it was launched from a developer laptop.

## 6. Why the first Docker image gave a different Alembic head

The repository at local commit `49310553` contained the October 30 migration. However, the already-running application image was about 40 hours old and reported the older head `20261007_doc_material`. The database also reported that older revision.

The Dockerfile showed no Alembic migration in its `CMD`, and the Compose app service had no custom entrypoint, no custom command that invoked migrations, and no bind-mounted application volume. The service command was Gunicorn.

We therefore built a fresh app image and ran Alembic's `heads` command in a temporary container based on that new image:

```bash
docker compose -f docker-compose.vps.yml build app

docker compose -f docker-compose.vps.yml run --rm --no-deps app \
  python -m alembic heads
```

The build completed successfully. The fresh image reported `20261030_shared_study_streak (head)`. A separate read-only SQL query confirmed the database still recorded `20261007_doc_material`.

This demonstrated the difference between:
- migration files present in the current source/image;
- migration revision recorded in the database;
- migration command actually applied to that database.

**Building an image does not run a database migration.** Replacing a container does not inherently upgrade the database either. Application startup and schema migration are separate operations in this Compose setup.

## 7. Frontend, backend, GitHub, Docker, and hosting

These are related parts of a delivery pipeline, but they are not the same thing.

### 7.1 Frontend and backend

The **frontend** is the user-facing application: screens, navigation, forms, state, and browser-side interactions. Prepza's frontend is built with the Node/pnpm toolchain. The Dockerfile runs:

```dockerfile
WORKDIR /build/frontend
RUN pnpm install --frozen-lockfile && pnpm run build
```

The frontend build produces static production assets in `frontend/dist`.

The **backend** is server-side application code. It handles trusted business rules, authentication/session checks, database operations, authorization, and server APIs. Prepza's Docker runtime uses Python 3.13 and Gunicorn to run `realtime_server:app`.

The frontend and backend are logically separated because they have different responsibilities and build/runtime toolchains. They can still be shipped together in one Docker image: the Dockerfile copies the compiled frontend assets into the Python runtime image:

```dockerfile
COPY --from=frontend-build /build/frontend/dist ./frontend/dist
```

This is a common deployment pattern. The browser downloads the static frontend assets, then makes HTTP/API requests to the backend. The backend validates the request, applies authorization/business logic, reads or writes PostgreSQL/Redis/storage as appropriate, and returns a response.

A logical frontend/backend separation does not require two separate hosting services. Separate services can be useful for independent scaling or deployment, but they add routing, CORS, configuration, and operational complexity. Prepza's current Dockerfile builds the frontend and serves its compiled assets alongside the Python application.

### 7.2 GitHub is source control, not the running server

GitHub stores the repository: source code, migration scripts, documentation, tests, configuration templates, and version history. A commit records a snapshot of tracked files.

A hosting provider runs the application. A typical delivery path is:

```text
Developer changes files
        |
        v
Git commit and push
        |
        v
GitHub repository (source + history)
        |
        v
Hosting build/deploy pipeline
        |
        v
Docker image
        |
        v
Running application container
        |
        +--> PostgreSQL
        +--> Redis
        +--> object storage / external providers
```

A document in GitHub does not automatically become a running service or a website page. It consumes repository storage in GitHub. It consumes hosting image/server storage only if the build process copies it into the image or separately deploys it.

### 7.3 What Docker does with repository files

The Docker build has a **build context**: the set of files Docker is allowed to send to the builder. `.dockerignore` removes files/directories from that context.

The current `.dockerignore` excludes items such as:
- `.git`
- environment files
- Node dependency folders
- generated frontend assets (which are rebuilt)
- Python bytecode/cache and test artifacts
- local audio/zip artifacts
- selected QA-only scripts and test requirements

It does **not currently exclude `docs/`**.

The Dockerfile contains `COPY . .` in both the frontend build stage and the Python runtime stage. Therefore repository documentation is currently part of the build context and is copied into those stages; because the runtime stage copies the repository, documentation is also present in the final runtime image unless excluded. The frontend build stage itself is not copied wholesale into the final image; only `frontend/dist` is copied from that stage.

This does not mean the docs are being served publicly. It means they occupy some space in the image filesystem/layers. The build context transferred in the observed build was approximately 3.77 MB. We have not yet measured how much image size would be saved by excluding docs.

A future optimization can exclude documentation from the Docker build context while retaining it in GitHub. Before changing `.dockerignore`, confirm that no runtime code, scripts, templates, or build steps read those documentation paths. Keep `alembic/` and migration files in the image if migrations are expected to be run from that image.

### 7.4 Docker image versus container

- **Dockerfile:** instructions for building an image.
- **Build context:** files available to the build.
- **Image:** immutable packaged filesystem/configuration created by the build.
- **Container:** a running or one-off instance created from an image.
- **Docker Compose:** describes and coordinates multiple services, their images/builds, networking, environment, volumes, and commands.

The local Compose stack includes PostgreSQL, Redis, app, chat-worker, and realtime services. Rebuilding only the app image does not rebuild every other service.

## 8. What must happen before data import

Do not import yet. The remaining work is a deliberate compatibility exercise.

1. **Verify the destination backup.** Keep the original local custom-format dump unchanged; optionally verify it again with `pg_restore --list`.
2. **Inspect all four pending Alembic migrations.** Confirm their preconditions and whether the source data already contains the target tables/columns.
3. **Compare matching table definitions.** For every table selected for import, compare column names/order, data types, nullability, defaults, constraints, indexes, and generated/identity behavior.
4. **Decide migration order.** If the local database must be upgraded first, rehearse the migrations against a disposable clone of the backed-up local database. Do not guess.
5. **Define a data-only import allowlist.** Exclude Supabase-managed schemas and infrastructure tables. Determine explicitly whether the app's `public.user` records and authentication fields are sufficient for local login. Do not assume that Supabase's `auth` schema can be restored into the self-hosted app.
6. **Handle foreign keys and import order.** Parent rows must exist before dependent rows unless the import procedure safely defers constraints.
7. **Handle sequences.** After importing explicit integer IDs, update each relevant sequence to a value that cannot collide with existing IDs.
8. **Protect sensitive data.** Do not print private messages, password hashes, payment details, access tokens, or user records into terminal logs or documentation.
9. **Use a disposable target first.** Test the exact data-only restore on a temporary database with the intended schema.
10. **Import into the working local database only after the rehearsal passes.**
11. **Verify counts and relationships.** Compare selected table counts, orphan checks, unique constraints, sequence next values, and application reads.
12. **Test local login and representative screens.** Existing-account login should be tested separately from signup email delivery. SES is not required merely to validate a pre-existing local password login if the application's login flow does not send email.
13. **Keep rollback possible.** If verification fails, restore the pre-import local backup into a separate recovery database or recreate the local database only under an explicit, reviewed recovery plan.

## 9. Known issues and lessons from the exercise

### Issue: direct Supabase hostname did not resolve from Docker

**What happened:** the direct database host could not be resolved in the container environment.  
**What we did:** used the project's Supabase Session Pooler connection details instead.  
**Lesson:** managed database access can use direct and pooled endpoints; network/DNS reachability is separate from credentials.

### Issue: initial password authentication failed

**What happened:** the first export attempt could not authenticate.  
**What we did:** reset the database password in Supabase and retried using environment variables.  
**Lesson:** distinguish authentication errors from DNS/network errors; never put credentials in source control or documentation.

### Issue: first `pg_restore` schema extraction failed

**What happened:** neither a database target nor output file was specified.  
**What we did:** used `-f /dev/stdout` and redirected the output to a host file.  
**Lesson:** command-line tools often require explicit input/output destinations; read the error and correct the invocation rather than treating it as archive corruption.

### Issue: stale Docker image reported an old migration head

**What happened:** current source had a newer migration but the running image did not.  
**What we did:** inspected Docker startup behavior, built a fresh image, and ran Alembic in a temporary container.  
**Lesson:** source code, built image, running container, and database schema are four distinct states.

### Issue: schema dump text differed

**What happened:** raw SQL diffs included dump metadata, ordering, comments, and sequence/default representation differences.  
**Lesson:** compare database structure semantically, not only as text. Sequence/default behavior must be checked before importing explicit IDs.

## 10. Resume and interview learning record

Once the migration is completed and verified, an honest project-based CV bullet could be:

> Designed and rehearsed a PostgreSQL data-migration workflow for a multi-service application, including custom-format backups, managed-database export, schema/version reconciliation with Alembic, selective data restoration, sequence and relationship validation, and post-migration application checks while preserving the destination schema.

Do not claim the data migration or login verification is complete until those steps have actually passed.

A concise interview explanation:

> I had an older managed PostgreSQL database with real application data and a newer local application schema. I first backed up the destination and exported the source in PostgreSQL custom format. I inspected the archive and compared the schemas instead of restoring the old schema over the new one. I then checked Alembic's migration chain and distinguished the code's migration head from the version recorded in the database. The remaining task is to rehearse a selective data-only import against a disposable database, validate relationships and sequences, and then test the application against the imported data.

## 11. Evidence log — append as work continues

| Date | Action | Result | Next action |
|---|---|---|---|
| 2026-10-30 | Created local backup and exported Supabase custom-format archive | Both files created; source archive passed `pg_restore --list` | Compare source/destination schemas |
| 2026-10-30 | Extracted public schema and inventoried tables | Local 112; Supabase 107; five local-only table names | Compare columns, constraints, indexes and sequences |
| 2026-10-31 | Inspected Dockerfile and Compose app startup | No automatic Alembic migration in app startup command | Rebuild image and inspect migration head |
| 2026-10-31 | Rebuilt app image from commit `49310553` | Build succeeded; build context approximately 3.77 MB | Inspect pending migration operations |
| 2026-10-31 | Compared Alembic code head with local DB revision | Image head `20261030_shared_study_streak`; DB `20261007_doc_material` | Review migration compatibility before applying |
| 2026-10-31 | Inspected migration filenames and revision variables | Confirmed `20261007_doc_material` is revision ID in `20261007_document_content_material_link.py` | Complete structural reconciliation |
| 2026-10-31 | Cloned the 112-table local backup to `prepza_migration_test_20261031` | Clone restored successfully; its Alembic revision and five target-table states matched the original local DB | Rehearse current migration head |
| 2026-10-31 | Diagnosed migration head mismatch | Running app container contained only migrations through `20261007_doc_material`; fresh image contained all four later files and head `20261030_shared_study_streak` | Use fresh one-off image, not stale running container |
| 2026-10-31 | Ran `alembic upgrade head` in a one-off container against `prepza_migration_test_20261031` | Process exited successfully; direct DB query confirmed revision `20261030_shared_study_streak` and all five Shop/streak tables exist | Verify columns, constraints, indexes, FKs and preserved data |

---

**Operating rule:** every future update to this guide must distinguish (1) what was attempted, (2) what actually succeeded, (3) the evidence, (4) what remains unverified, and (5) what was learned. Never turn a planned step into a completed claim.


## 12. Migration rehearsal — disposable clone and Docker image diagnosis (2026-10-31)

### 12.1 Why a disposable clone was created

Before testing pending migrations, the local pre-change backup was restored into a separate database named `prepza_migration_test_20261031`. This gave us a realistic copy of the destination schema without risking the working `prepza` database.

The clone restored without errors and contained 112 public tables. Its Alembic revision was `20261007_doc_material`. Its Shop tables (`shop_listing`, `shop_saved_listing`, `shop_report`) were missing, while `study_friend_streak` and `study_friend_streak_activity` already existed. The original local database showed the same five-table state.

### 12.2 The stale-container diagnosis

The first migration attempt used the running `app` container. Alembic reported `20261007_doc_material` as its head, and the four newer migration files were absent from that container.

A temporary container created from the rebuilt image showed:

- `python -m alembic heads` → `20261030_shared_study_streak (head)`
- The files `20261027_shop_marketplace.py`, `20261028_shop_listing_expiry.py`, `20261029_shop_period_payment.py`, and `20261030_shared_study_streak.py` were present.

This is the practical difference between a rebuilt image and an already-running container: rebuilding an image does not automatically replace the old running container. `docker compose run --rm --no-deps app ...` created a one-off container from the current image without replacing the running app service.

### 12.3 Exact safe migration command used

The command reads the app's configured `DATABASE_URL`, changes only the database name to the disposable clone, and invokes Alembic in a subprocess:

```bash
docker compose -f docker-compose.vps.yml run --rm --no-deps app python -c '
import os
import subprocess
import sys
from sqlalchemy.engine import make_url

url = make_url(os.environ["DATABASE_URL"]).set(
    database="prepza_migration_test_20261031"
)

env = os.environ.copy()
env["DATABASE_URL"] = url.render_as_string(hide_password=False)

print("Migration target:", url.database, flush=True)

subprocess.run(
    [sys.executable, "-m", "alembic", "upgrade", "head"],
    env=env,
    check=True
)

print("Migration command completed successfully.", flush=True)
'
```

Observed output included the intended target database and `Migration command completed successfully.`. This is evidence that the subprocess returned exit code 0. It is **not yet sufficient evidence** that the expected database revision and objects are present; database-side verification is the next required step.

The earlier attempt that imported Alembic's `main` function into the parent Python process returned without applying migrations. The corrected subprocess invocation avoids ambiguity around Alembic's CLI entry point and gives the process an explicit environment.

### 12.4 Verification commands still required

After the migration process, query the clone directly:

```bash
docker compose -f docker-compose.vps.yml exec -T postgres \
  psql -U prepza -d prepza_migration_test_20261031 -P pager=off -c "
SELECT version_num FROM alembic_version;
"
```

Then verify the three Shop tables and the two streak tables through `information_schema.tables`, and inspect columns, indexes, constraints, and foreign keys. Also verify that pre-existing document/material records remain intact. Do not proceed to the Supabase data import until these checks pass.

### 12.5 What a working engineer memorises

Engineers generally do **not** memorise every long command. They learn the concepts, recognise common tool patterns, know where to find authoritative documentation, and understand the risks of each operation. In day-to-day work they use shell history, repository README/runbooks, Makefiles, scripts, IDE tasks, CI workflows, and command help (`--help`). They must still understand what a command targets before running it.

Useful command patterns from this exercise:

| Pattern | Purpose | Risk to understand |
|---|---|---|
| `docker compose exec SERVICE COMMAND` | Run inside an existing container | Uses the existing container's filesystem/image |
| `docker compose run --rm --no-deps SERVICE COMMAND` | Start a temporary one-off container | Uses the service image/config; command can still mutate connected services |
| `pg_dump -Fc` | Create a custom-format backup | Must capture the intended source database |
| `pg_restore --list` | Inspect archive contents | Does not prove destination compatibility |
| `psql -c "SELECT ..."` | Run SQL against a selected database | The `-d` target matters |
| `python -m alembic heads/current/history` | Inspect migration graph/state | Reads migration files and connects according to configuration |
| `python -m alembic upgrade head` | Apply pending schema changes | Mutates the database in `DATABASE_URL` |
| `git status/log/diff` | Inspect source-control state | Does not show live database state |

A reliable workflow is: identify the target, inspect the command's effect, take/verify a backup, rehearse on a disposable copy, execute once, then verify the resulting state. Looking up syntax is normal; understanding the impact is the professional skill.


### 12.6 Database-side verification result (2026-10-31)

Directly queried `prepza_migration_test_20261031` using the PostgreSQL service after the one-off migration command:

- `alembic_version.version_num` = `20261030_shared_study_streak`.
- `shop_listing` = EXISTS.
- `shop_saved_listing` = EXISTS.
- `shop_report` = EXISTS.
- `study_friend_streak` = EXISTS.
- `study_friend_streak_activity` = EXISTS.

This confirms that the disposable clone advanced to the expected Alembic head and the five expected tables are present. It is a **partial migration rehearsal PASS**, not yet full schema/data-integrity PASS. Column definitions, check/unique constraints, indexes, foreign keys, and preservation of pre-existing records still require inspection before any production-like local database migration or data import.
