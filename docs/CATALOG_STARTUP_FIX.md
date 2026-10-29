# Existing database: catalog upgrade pending

The Overview loads both the dashboard and the indexed opportunity API. Older databases can contain opportunities without typed catalog projections; the indexed API correctly returned 409 instead of silently hiding those records, and that dependency blocked the whole Overview. Schema migration alone did not perform the separate data backfill. Fresh-database acceptance tests did not catch this upgrade path.

## Repair the current installation

Docker, from the project directory:

```powershell
docker compose exec backend python -m app.catalog_migrations backfill
```

Native Windows, using the same backend environment and working directory as the API:

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.catalog_migrations backfill
```

Refresh the browser. Do not delete the database, regenerate encryption keys, or remove volumes. This command fills missing projections in resumable batches and preserves opportunity IDs, source links, applications and private records.

## Source correction

Local API startup now performs the idempotent projection backfill after schema migration and before serving requests. `AUTO_CATALOG_BACKFILL` defaults true locally and false in production, where operators still use the controlled deployment/backfill procedure. Existing local dotenv files need no new setting; Compose defaults true. Explicit opt-out is supported. Readiness returns 503 while any canonical rows remain unprojected, and the Windows launcher checks readiness before opening the app. No automatic heavy data upgrade is enabled by default for production.

The error wording referred to indexing, but this repair is the typed-data backfill. PostgreSQL search indexes remain the separate `python -m app.catalog_migrations indexes` deployment operation. It is not necessary to delete/reingest listings or bypass the indexed API guard.

Regression tests insert legacy rows through Core SQL, reproduce the 409 from the indexed API and 503 readiness, run actual startup preparation, and verify indexed opportunities, dashboard and readiness succeed afterward. IDs and source membership survive and a second startup is safe. A separate opt-out test verifies requests stay unready until an explicit operator backfill. Runs use isolated SQLite; no user's actual database was accessed or repaired remotely. See `artifacts/catalog-startup.json` and `.xml`.

Executed: 24 startup/hosting tests passed; API/catalog regressions passed 19 tests with two PostgreSQL-only skips. OpenAPI type drift and local Compose validation passed. No production migration, native Windows startup or new Docker image build was executed in this environment.
