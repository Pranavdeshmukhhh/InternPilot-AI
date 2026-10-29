# Phase 7 performance and reliability evidence

Date: 2026-10-28–29 UTC. **Verdict: not ready for unrestricted multi-tenant production or production-scale performance claims.** Functional/recovery regressions pass; large-catalog concurrent latency and security boundaries still need work. See [SECURITY_REVIEW.md](SECURITY_REVIEW.md) for corrected defects and remaining risk.

## Environment and method

Actual execution: Linux x86-64; Python 3.12.14; Node 24.19.0; native PostgreSQL 16.15; one FastAPI/Uvicorn process. Cgroup CPU quota `200000/100000` = two cores; memory limit 8GiB. PostgreSQL: 64MiB shared buffers, 4MiB work_mem, 50 max connections, 128MiB max_wal_size. API pool: five base + two overflow. Test data lived on the isolated `/tmp` filesystem, with about 4.2GiB free after cleanup. This is not the Docker/cloud reference deployment.

`scripts/benchmark-production.py` creates/drops a random schema in a marked local, non-superuser-owned database. It refuses production/remote databases and insufficient disk headroom. All source configurations are disabled; no discovery workers/provider credentials, uploads, submissions, email or public HTTP traffic are involved.

Each scenario contains 20 synthetic users, 1,000 source configurations and the stated **global** opportunity count. A user owns 50 sources and sees approximately 1/20 of the catalog: 500, 5,000 or 50,000 records. Facts are shared records; private saved state remains separate. Fixtures use short descriptions, one location, open internships, varying companies/remote flags, selective PyTorch matches and future deadlines. These compact, uniform fixtures underrepresent long descriptions, fragmented histories, many matches/saves/applications, changing eligibility and broad single-user subscriptions.

The driver warms each user once, then runs a closed workload for 20 seconds with 50ms think time. Approximately 40% newest pages, 20% full-text search, 10% company substring search, 10% deadline pages, 10% profile reads and 10% actual bookmark writes. Returned pages are bounded to 20 records. Report elapsed time includes draining in-flight requests. The offered rate falls when the server slows; this is **not** a fixed-arrival 50-RPS test. No TLS, network throttling, Redis/SSE, cloud failover, cold-cache or sustained soak certification.

## Latest measured HTTP results

| Global records | Clients | Requests | p50 ms | p95 ms | p99 ms | RPS | Errors | Peak RSS MiB* | Mean CPU cores* |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 10,000 | 10 | 663 | 245.7 | 398.6 | 448.5 | 32.80 | 0 | 495.7 | 1.16 |
| 100,000 | 25 | 402 | 1227.6 | 1975.2 | 2433.0 | 18.98 | 0 | 965.8 | 1.30 |
| 1,000,000 | 25 | 84 | 6843.6 | 11735.9 | 13608.7 | 3.12 | 0 | 1248.7 | 1.52 |

*Process-tree samples every 250ms during HTTP load, including API/PostgreSQL children. RSS sums double-count shared pages and exclude unmapped filesystem/cache memory; these are not whole-container peaks or minimum server-sizing recommendations. CPU is process CPU time divided by sampled wall time. Raw samples are summarized, not field telemetry. Only 84 requests completed in the largest run; p99 there is a coarse near-maximum observation. Individual endpoint sample counts and SQL timings are retained in JSON.

Latest evidence: [10k](../artifacts/phase7-10000-release.json), [100k](../artifacts/phase7-100000-release.json), [1M](../artifacts/phase7-1000000-release.json), [summary](../artifacts/phase7-performance-summary.json). Approximate schema sizes: 15.5MiB, 140.5MiB and 1,426MiB. Seeding/indexing took 0.60s, 4.64s and 53.53s respectively. SQL-generated fixture insertion is not production ingestion throughput.

Existing architecture targets remain **p95 <=300ms, p99 <=1s at 50 read RPS**, overview <=200ms, with a declared mixed-workload reference environment. They have not been met/certified here. Even the lighter closed workload shows material latency problems. Zero observed errors is not a scalability pass. Benchmark JSON uses `correctness_passed`, `workload_class` and `production_acceptance_certified:false` to preserve that distinction.

## Query corrections and comparison

`catalog_query.py::indexed_query` previously resolved every membership through `Opportunity + COALESCE`, then eager-joined canonical facts even though the indexed path admits only canonical rows. The new `visible_predicate` reads direct IDs from narrow membership tables and unions only actual legacy aliases; the semi-join preserves tenant authorization and avoids duplicate output. `lazyload(Opportunity.canonical)` removes the unnecessary eager join on this canonical-only path. A partial `ix_catalog_unprojected` makes the legacy-indexing guard cheap when backfill is complete. The existing online index command installs it; no schema-version/column/data change.

Seven alternating warm single-client trials compare the current cursor path with the inspected source at fixed commit `eedcf4c`, using the **same indexed schema, profile, saved state and returned IDs**. Both include scoring/decoration; the old path also benefits from indexes present in the common schema. This isolates query shape conservatively, not the entire old/new deployment.

| Global records | Visible/user | Prior median | Current median | Interpretation |
| --- | --- | --- | --- | --- |
| 10k | 500 | 43.48ms | 43.75ms | Effectively unchanged at this sample size. |
| 100k | 5,000 | 89.73ms | 62.44ms | 30.4% lower median in this run. |
| 1M | 50,000 | 637.07ms | 481.32ms | 24.4% lower median in this run; still too slow under concurrency. |

Seven samples do not establish a reliable tail SLO. cProfile top cumulative functions and `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` plans are stored in each scenario. The compact page uses four catalog/decorating SQL statements, plus two authentication reads; count remains bounded as records grow. Driver instrumentation records per-statement aggregate duration and per-request SQL count/time, with no bound values/credentials. PostgreSQL relation scan/tuple statistics are also retained.

**Rejected optimization:** an initial OR/correlated-membership rewrite passed correctness tests but produced p95 6.13s at 100k. It was rejected and replaced with the union strategy. Its [10k](../artifacts/phase7-10000-rejected-query.json) and [100k](../artifacts/phase7-100000-rejected-query.json) measurements remain available. Its 1M run was interrupted during index construction, before HTTP load; there is no completed result for that attempt. The interruption also exposed and led to the invalidated-connection RESET correction in `catalog_migrations.py`.

Authentication now releases its short transaction before endpoint processing; sensitive mutations still re-lock/revalidate. Its individual performance contribution was not isolated. Profile p95 rises from 217ms at 10k to 3.34s in the 1M mixed run despite small SQL work, showing shared resource/scheduling pressure. Pool-acquisition wait, event-loop lag, lock graphs and allocation flame graphs were not separately measured; do not infer a proven root cause from that gap.

## Queue, failures and recovery

Each latest scenario also enqueues 1,000 synthetic durable read tasks, expires one claimed worker lease, recovers it, and claims/completes all tasks with four threads. No crawler/network work is executed by this timing probe.

| Catalog | Unique completions | Claim/complete rate | p95 task lag | End depth | Recovered lease |
| --- | --- | --- | --- | --- | --- |
| 10k | 1,000 | 144.17/s | 7.20s | 0 | 1 |
| 100k | 1,000 | 128.38/s | 7.82s | 0 | 1 |
| 1M | 1,000 | 125.87/s | 8.23s | 0 | 1 |

Lag includes initial sequential enqueue time. This is database queue evidence, not opportunities/second, provider throughput or whole-worker capacity. Controlled backend tests separately cover 1,000 fixture sources/real parsers over in-memory HTTP transports, 429/Retry-After, circuit cooldowns, bounded global/host permits, cancellation/lease expiry, partial pagination replay, duplicate execution, owner fairness, queue overload/dead letters, inference budgets and upload/send/submit checkpoint recovery. See `tests/test_distributed_discovery.py`, `test_discovery_fairness.py`, `test_worker_reliability.py`, `test_api_worker.py`, `test_outreach.py` and `test_phase7_security.py`.

The [real logical restore drill](../artifacts/phase7-recovery.json) used two newly created local databases. A 59,446-byte authenticated encrypted pg_dump backup decrypted/restored successfully; encrypted profile/document bytes, plaintext document contents, application/document references and schema v1–v7 history survived. Repeated migration was idempotent and workers remained paused. Tampering failed authentication and the incomplete plaintext file was removed. Measured backup 0.16s, restore+verification 0.99s, complete small drill 3.35s. **These are not full-size RTO/RPO figures.** Offsite restore, missing keys, full-volume artifacts, PITR and external-side-effect reconciliation still need operator drills.

## Regression, frontend and security validation

- Final backend run: **556 passed, 2 skipped, 1 warning in 185.57s**, exit 0. [JUnit](../artifacts/phase7-final-backend.xml), [execution metadata](../artifacts/phase7-final-backend.json). Includes 28 PostgreSQL parameter variants. The two skips are the SQLite variants of PostgreSQL-only row-lock/planner cases; PostgreSQL counterparts executed. Existing Starlette/httpx TestClient deprecation warning remains. Earlier full runs: 552 passed before the output-error backup test, then 553 passed before the three private-IPv6 syntax cases.
- Frontend lint, TypeScript, five query/transport tests, OpenAPI type drift check, Prettier check and production build: passed. Workspace First Load JS 155kB. Next emits an ESLint-plugin configuration warning; no build/type errors.
- Phase 7 production-browser rerun: **20 product checks passed**, 11 axe screen/theme evaluations without serious/critical findings; widths 320–1920px, fresh touch context, keyboard/focus/reduced-motion, actual generated PDF download, queued draft application, source create/delete, event/form retention and same-tab account isolation. [Report](../artifacts/phase7-ui/report.json). Visibility signals were explicitly simulated in headless Chromium. No real external provider actions. No screen-reader/real-device certification.
- Phase 6 original-build comparison remains immutable in [phase6-performance.json](../artifacts/phase6-performance.json): 10→0 API requests in a 17s idle explorer window, row 147→121px, decoded JS 599,856→547,323 bytes. This excludes the server's SSE SQL polling and is not a zero-background-load claim. Local observer vitals are single-run samples; full-suite viewport/navigation changes include some CLS >0.1. No field p75 Core Web Vitals claim.
- Dependency audits: zero currently reported Python lockfile/npm advisories after the four upgrades; pip check passed. [Summary](../artifacts/phase7-dependencies.json) and raw before/after reports are retained. Known-advisory absence is not proof of security. Docker now installs the audited version-pinned lock, rather than resolving an unpinned transitive graph.
- Ruff and `git diff --check`: passed. CI helper was actually exercised locally: non-superuser role, synthetic marker and cleanup verified. Hosted GitHub Actions, Docker image builds, cloud deployment and HTTPS ingress were not executed.

## Reproduce safely

Use the backend virtual environment. Never supply production DSNs. The local lab database must be named `phase4_*` or `phase7_*`, owned by a non-superuser, with comment exactly `InternPilot Phase7 synthetic benchmark only` (the existing Phase4 marker is also accepted). Supply URLs through environment variables, not command arguments/logs. CI creates its own role/database with `scripts/prepare-ci-database.py`; that helper intentionally requires GitHub CI context.

```sh
# PHASE4_POSTGRES_URL points only to the marked local test database.
backend/.venv/bin/python scripts/verify-backend.py --postgres --output-prefix artifacts/phase7-final-backend -- -q -ra

# PHASE7_POSTGRES_URL points to the same disposable lab.
backend/.venv/bin/python scripts/benchmark-production.py --records 10000 --concurrency 10 --seconds 20 --queue-tasks 1000 --pg-data-dir /path/to/disposable/pgdata --confirm-synthetic-only --output artifacts/phase7-10000-release.json
# Repeat with --records 100000 and 1000000, --concurrency 25; use distinct reports.

# Requires pg_dump/pg_restore on PATH and explicit local PHASE7_ADMIN_URL.
backend/.venv/bin/python scripts/verify-recovery.py --pg-data-dir /path/to/disposable/pgdata --confirm-synthetic-only

cd frontend
npm run lint && npm run typecheck && npm test && npm run types:check && npm run format:check && npm run build
cd ..
UI_ARTIFACT_DIR=artifacts/phase7-ui backend/.venv/bin/python scripts/run-ui-acceptance.py --phase6-ui
```

The UI runner needs free localhost 3000/8000 and Chromium; backend tests use isolated local services. For Windows use the virtual environment's `Scripts/python.exe` or Linux containers/WSL. POSIX parser resource limits were verified on Linux; equivalent native Windows memory/CPU isolation is unverified. The restore helper intentionally requires a disposable local PostgreSQL cluster administrator and verifies its data_directory; it drops only the random databases it created. Preserve production keys separately and keep all outbound workers stopped throughout a real recovery.

## Ordered next gates and production checklist

1. **P0 security boundary:** enforce socket/proxy/runner egress against DNS rebinding and metadata/private ranges; isolate parser/browser UID/filesystem/credentials. Keep unsupported submission adapters disabled. See security review.
2. **P1 bounded hot reads:** profile ID-only ordered membership plans before loading facts; evaluate efficient alias/direct membership strategies with existing indexes. Avoid the rejected OR shape. Materialize versioned matches and summaries to remove v1/dashboard/reminder request-time history scoring; preserve v1 semantics until migration is complete.
3. **P1 contention/admission:** instrument connection acquisition, transaction age, lock waits and event-loop lag; bound expensive reads/uploads/streams per user; reserve operational capacity. Enforce DB statement/lock/idle-transaction budgets using provider-compatible settings. Measure before enlarging pools.
4. **P1 durable updates/fanout:** committed event/outbox/revision processing and shared publisher intent scheduling; reduce per-user subscription task duplication and SSE polling. Verify reversed commits, replay and Redis loss with independent assertions.
5. **P1 acceptance workload:** implement the existing blueprint's five-minute warmup, 15-minute steady, burst/recovery, repeated warm/cold runs and two-hour mixed crawler/API/matching soak. Include long descriptions, realistic closed records/application histories, actual SSE clients, tenant churn, storage exhaustion and DB/Redis restarts. Current short smoke is not that harness.
6. **P1 recovery/deployment:** full-size offsite encrypted restore with matching keys/artifacts, current suppression/consent records and receipt reconciliation; canary HTTPS deployment, resource limits and incident alerts. Rehearse physical rollback without replaying external actions.

| Gate | Result |
| --- | --- |
| Functional regressions, tenant checks, bounded pages and deduplication | Locally verified by executed tests. |
| Approval/checkpoint/uncertain-outcome safeguards | Local fixtures verified; real adapters not certified. |
| Dependency scans and version-pinned application image inputs | Verified pins/scans; actual Docker image build unverified. |
| Small encrypted database restore and tamper rejection | Verified; production RPO/RTO/PITR unverified. |
| UI build/keyboard/responsive/automated accessibility | Verified local coverage; field/device/screen-reader gaps remain. |
| Architecture 50-RPS / p95 300ms target | **Not achieved/certified.** Larger closed workloads are already too slow. |
| DNS/socket boundary, independent runner privileges, complete tenant defense | **Open release blockers** for untrusted multi-tenant service. |
| Cloud HA, 24/7 soak, operational capacity and deployed monitoring | **Unverified.** No hosting performed. |

The application is a locally verified build for controlled evaluation. The evidence does not justify calling it production-ready at the requested multi-user scale.
