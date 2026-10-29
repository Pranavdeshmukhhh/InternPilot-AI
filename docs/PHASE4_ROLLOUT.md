# Phase 4 catalog rollout and recovery

## Compatibility boundary

Schema version 6 is additive. The existing SQLAlchemy numbered runner remains the only migration authority; Alembic has not been introduced. Existing opportunity IDs and application/document/saved references remain valid. Reviewed public facts use global fingerprints. Historical private IDs can become aliases, with their original payload encrypted in `opportunity_archives`. Profiles, matches, credentials, application outcomes and saved state remain owner-scoped. Arbitrary feeds/imports are private; a user's permission checkbox cannot approve public sharing.

Do not run pre-v6 writers alongside v6 writers. The fresh-install bootstrap still uses current SQLAlchemy metadata; this phase does not rewrite the complete historical migration system.

## Forward rollout

1. Back up PostgreSQL, protected document storage and encryption keys separately. Restore that backup into an isolated database and verify application/document references before proceeding. Do not put production credentials into command arguments or logs.
2. Stop API writers and all schedulers/workers. Keep the old image and backup available. Set the normal server environment using your existing secret mechanism.
3. From `backend`, run `.venv/bin/python -m app.migrate`. In a container use its installed `python`. Version 6 adds tables/columns without deleting existing facts. New reverse-link/owner indexes are built during this migration and may briefly block writes; schedule this step in a maintenance window for large tables.
4. Run `.venv/bin/python -m app.catalog_migrations backfill`. Projection backfill commits bounded batches and can be rerun after interruption. It does not promote historical private data to public.
5. Run `.venv/bin/python -m app.catalog_migrations indexes`. PostgreSQL opportunity/FTS indexes are built concurrently, outside the migration transaction. Lock acquisition times out after five seconds; rerun after resolving contention. Interrupted invalid ordinary/FTS indexes are repaired on rerun. Default full text uses the `simple` configuration. Do not enable `--trigram` without a repeated company-substring workload and measured plan benefit; extension installation needs database permission.
6. Start one v6 API/worker canary. Verify existing IDs, saved items, application/document references, a private source and a reviewed shared source with two isolated test users. Repeated cached scans must retain provider timestamps and must not duplicate public facts.
7. Resume workers gradually. Monitor connection counts, source lease conflicts, task retries, query latency, duplicates and notification counts. There is no automatic proof that an external application succeeded.

No production database has been migrated as part of the implementation tests. These commands require operator execution against the intended environment.

## Source publication policy

Six built-in publishers are registered from code-reviewed defaults. An operator may approve a specific public Greenhouse/Lever/Ashby/SmartRecruiters slug using:

```
python -m app.catalog_migrations approve-ats --source-id SOURCE_UUID --confirm-public-review
python -m app.catalog_migrations revoke --source-id SOURCE_UUID --confirm-public-review
```

Review attribution and permission first. Custom URLs cannot be approved through this command. Revocation clears the shared lease and blocks new automatic preparation from that registry. Cached facts may remain available as historical records. Company attribution for shared ATS facts comes from the reviewed registry, never another user's display label.

## Query compatibility

The v1 endpoint and advanced recommendation semantics remain available. Chronological projected v1 queries use SQL prefilters and exact counts. Authenticated `/api/v2/opportunities` provides bounded newest/deadline pages without exact totals; its encrypted, one-hour cursor binds owner, filters and page size. Changing filters requires a fresh cursor. Backfill is required before v2 serves visible legacy rows; otherwise it returns a clear conflict response. Explicit `search_mode=text` uses PostgreSQL FTS; SQLite rejects that mode instead of claiming equivalent search. Default substring search remains compatible.

V1 score/recommendation and dashboard paths still perform personalized full-history work. Frontend adoption of v2, materialized matches, global scheduler fanout reduction and distributed rate budgets are later work, not delivered scalability guarantees.

## Recovery

1. Stop every writer and preserve a fresh backup of the failed rollout for investigation. Never replay submissions or email sends during recovery.
2. Prefer rolling forward with v6 and resumable backfill/index commands when the schema is intact.
3. For a reader compatibility recovery, with the original encryption key available, run `python -m app.catalog_migrations materialize-aliases --writers-stopped`. It restores original encrypted private snapshots where available, otherwise canonical facts, into the original IDs. IDs and references survive; v6 columns/tables/version remain. The operation is idempotent, bounded and tested in SQLite/PostgreSQL fixtures. Rerun projection backfill before restoring v6 cursor traffic.
4. A physical pre-v6 downgrade requires restoring the verified full database/files backup with the matching application image and keys. Do not drop columns or decrement migration history manually. This implementation does not claim a destructive down migration is safe.

## Pool budget

Defaults per API/worker process: `DB_POOL_SIZE=5`, `DB_MAX_OVERFLOW=2`, `DB_POOL_TIMEOUT=15`, `DB_POOL_RECYCLE=1800`. Budget `(API processes + worker processes) * (pool size + overflow)` plus migration/monitoring headroom against PostgreSQL `max_connections`. Streaming authentication releases its session immediately; SSE polling still performs periodic short database reads.

## Reproducible verification

```
cd backend
.venv/bin/ruff check app tests
.venv/bin/python -m pytest -q -p no:cacheprovider
```

Set `PHASE4_POSTGRES_URL` to a disposable test database to additionally exercise PostgreSQL schema fixtures, concurrency and FTS. Tests create and drop only random per-test schemas. Never point it at a production database. Frozen genuine schema v1/v5 fixtures test migration twice and reference preservation.

The microbenchmark requires a local, non-superuser-owned database named `phase4_*`, marked with database comment `InternPilot Phase4 synthetic benchmark only`. Supply the URL through the environment:

```
backend/.venv/bin/python scripts/benchmark-phase4.py --records 10000 --repeats 5 --confirm-synthetic-only --output artifacts/phase4-query-10000.json
```

The script refuses insufficient disk headroom and removes its random schema on completion. It compares page IDs, statement counts, Python rows examined, warm timings and query plans. It is a single-client query comparison, not an HTTP throughput, 1,000-source, cloud or concurrent-user certification.
