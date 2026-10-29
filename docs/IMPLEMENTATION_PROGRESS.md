# Phase 4 implementation progress

2026-10-28. Implemented directly in the existing repository after reading the engineering audit, production architecture, implementation handoff and actual source. No production data migration, external application, outreach or deployment performed.

## Decisions and implemented milestones

- Preserved the existing audited source as commit `71ef94a` before Phase 4. Unrelated historical screenshots/manifests remain outside Phase 4 commits.
- Schema v6 retains the existing SQLAlchemy numbered migration authority. Additive catalog projections, source registry, membership, encrypted private archives and self-referencing compatibility aliases preserve old opportunity IDs and application/document/saved references. Genuine frozen schema v1/v5 fixtures exercise upgrades. Fixed a historical migration-3 bootstrap incompatibility exposed by the genuine v1 fixture.
- Shared public facts and source fetch leases are restricted to operator-reviewed publishers; custom feeds/imports remain private. Public publisher attribution cannot inherit personal source labels. Source generation, task attempt and publication lease checks fence stale writers. Historical private payloads are encrypted before alias consolidation.
- Batched, consistently ordered transactional upserts use database fingerprint uniqueness. Cached subscribers link existing facts without rewriting them. Batched source memberships, notifications, saved-change fanout and source permission lookup remove per-opportunity database work from those paths. Application lists eager-load jobs; duplicate application checks include legacy aliases and canonical URLs.
- Indexed SQL prefilters accelerate chronological v1 requests while preserving its exact totals and fallback semantics. Authenticated v2 adds owner/filter-bound stable cursors, newest/deadline order and explicit PostgreSQL FTS. Trigram remains optional and requires query evidence. Backfill is bounded/resumable; opportunity indexes build concurrently in PostgreSQL.
- Configurable connection pools and shorter SSE session lifetimes reduce connection occupancy. Deadline reminder queries prefilter before loading/scoring bodies. Frontend/API compatibility retained; no UI rebuild.

## Verification ledger

Intermediate runs (not final certification): 10 passed; 68 passed; 27 passed; 12 PostgreSQL/SQLite core tests passed; 19 passed/1 skipped after fixture parser correction. First full regression run: 505 passed, 1 skipped, 3 failed. Two failures were stale migration-version assertions; one was an outreach test assuming local midnight was always over an hour away. Corrected expected v6 history and asserted next sender-local calendar date without changing outreach behavior. One attempted later run was interrupted by a tool-output broken pipe; it is not counted as passed.

Final regression results and benchmark figures are recorded below after execution. Ruff (`cd backend && .venv/bin/ruff check app tests`) and `git diff --check` executed successfully during final review.

PostgreSQL tests use native PostgreSQL 16.15 extracted from the cached image into disposable `/tmp` storage. Docker container startup was abandoned because its filesystem layer exceeded workspace headroom. No live user database or secrets were used. Test role is non-superuser; randomized schemas are dropped after tests.

## Recovery and deployment

See [PHASE4_ROLLOUT.md](PHASE4_ROLLOUT.md) for backup/restore, writer shutdown, migration/backfill/online indexes, canary checks, source approval/revocation, pool budgets and alias materialization recovery. Recovery is tested on synthetic schemas; physical production backup restoration has not been performed. Keep original encryption keys available. Never run old and new writers together.

## Remaining limitations

- V1 personalized score/recommendation and dashboard paths still scan visible history. V2 avoids that work, but frontend migration and materialized matches are separate work.
- Per-user subscription scheduling remains, although shared provider fetches/facts and unchanged-profile cached work are coordinated. No claim of 1,000-source throughput or thousands of concurrent users is made.
- Sync SQLAlchemy remains inside some async service paths; this phase reduces query volume rather than converting the entire service to async SQLAlchemy.
- Opaque legacy fingerprints are conservatively retained privately until verified consolidation is possible. A URL match alone cannot authorize publication of private facts.
- Reverse membership/owner index additions in v6 still need a maintenance window on large existing tables; PostgreSQL opportunity/FTS builds use concurrent DDL.
- Expired shared leases reject stale writes; some abandoned crawl-run diagnostics may remain running until retention/recovery. No external success is inferred from preparation.
- PostgreSQL row-level security, global scheduler replacement, materialized matching, durable event outbox and frontend v2 adoption are not represented as completed.
- Large-scale mixed HTTP/crawler load tests and physical cloud failover remain unexecuted. Query microbenchmarks are single-client warm comparisons only.

## Final regression execution

`pytest -q -p no:cacheprovider --junitxml=../artifacts/phase4-backend-tests.xml` with isolated SQLite control state and PostgreSQL fixture URL: **515 passed, 2 skipped, 1 warning in 184.79 seconds**, exit 0. The two skips are PostgreSQL-only cases in the SQLite parameterization; PostgreSQL variants executed. Existing Starlette/httpx TestClient deprecation remains. Full log: `artifacts/phase4-test-output.log`; JUnit: `artifacts/phase4-backend-tests.xml`. Ruff and whitespace checks passed. No frontend source changes; no frontend build or browser test was rerun in this backend phase.

## Benchmark method correction

Review caught that the initial baseline inherited v6 alias-resolution expressions, overstating the old path's cost. Those timings are rejected. The final benchmark freezes the pre-v6 physical-JSON source-membership query and Python heap selection from baseline `71ef94a`, compares identical first-page IDs, and includes five measured warm repetitions after warm-up. Both paths hydrate/score/decorate the selected page. The v2 path intentionally omits exact totals, so it is reported separately. An obsolete 100k run was interrupted and its random schema cleaned before rerunning the corrected script.

## Final measured query comparison

PostgreSQL 16.15, local warm single client, 20-item first page, five measured samples per path after warm-up, synthetic data only. Same page IDs verified. Final implementation commit: `7721bb4`.

| Records | Legacy Python + exact total | Indexed v1 + exact total | Cursor v2 without total | v1 speedup |
|---:|---:|---:|---:|---:|
| 10,000 | 0.597711 s | 0.112274 s | 0.082427 s | 5.32x |
| 100,000 | 4.835324 s | 0.827766 s | 0.592928 s | 5.84x |

Reports include all samples, SQL counts and EXPLAIN ANALYZE/BUFFERS plans. Baseline examines 8k/80k Python candidate facts; indexed paths avoid the full-history Python scan and only hydrate/score the selected page. The 100k indexed v1 median remains 0.828 s: useful improvement, not attainment of a sub-200 ms production SLO. Membership authorization, exact counts and bounded-page hydration need further profiling at larger scale. No 1M run: the script requires ~4.1 GB workspace headroom and this environment has ~733 MB. No mixed-user HTTP/crawler benchmark or real production rollout was performed.

# Phase 5 — distributed discovery and reliable automation

Continued from verified Phase 4 commits `7721bb4` and `7d47305`. Read the actual queue, host budgets, shared source catalog, connectors, migrations, matching, outbound checkpoints, owner authorization and architecture/handoff before editing. No deployment, public stress traffic, real applications or outreach performed.

## Implemented milestones

1. **Admission and fault domains:** additive schema v7 (`coordination_state`, `request_leases`, `discovery_health`); cluster-wide PostgreSQL global/host in-flight HTTP permits; existing shared host spacing plus configurable stricter per-host policies; hard stream deadlines; cancellation cleanup and crash expiry; shared publisher failure cooldowns; Retry-After on 429/503; bounded exponential jitter and slower authorization-denial retries. Personal imports/feeds remain private. Public registries/caches still serve multiple subscribers without repeated network fetches.
2. **Durable execution:** serialized global/per-owner queue admission; 503/Retry-After on API overload; scheduler stops admitting at capacity; per-owner least-recent dispatch with intra-owner priorities; worker role pause/resume with audited owner controls; bounded worker retries/dead-letter state; failed source intents require explicit retry; attempts fence all outbound checkpoints; expired task acknowledgments cannot suppress recovery. Queue claims, renewals and maintenance use threads for short sync database operations. Legacy bulk discovery uses fixed consumers and a bounded queue rather than a coroutine for every configured source.
3. **Discovery/matching:** bounded rolling Workday API pagination; every run checks page zero; exact failed-offset recovery; successful uncommitted pages are retained durably until facts commit; resumed/partial inventories cannot close absent postings; closing evidence includes source/time. AI enrichment skips shared cache subscribers, remains non-authoritative, uses deterministic eligibility for private profiles and has a durable global daily request cap, per-scan cap and time budget. Existing application/outreach approval, suppression, quota, checkpoint and confirmation checks retained.
4. **Operations and evidence:** owner-only pause controls; tenant-isolated source diagnostics; explicit safe read-task retries; existing dashboard worker status exposes pause state; new controlled failure/concurrency tests and [operations/runbook](PHASE5_OPERATIONS.md). `.env.example` documents tuning. No new service/broker dependency.

## Validation history

- Initial targeted regressions: **94 passed, 2 skipped**, 10.39 s.
- New controlled SQLite tests: **5 passed**, 1.84 s; 1,000 synthetic feed sources / 2,000 in-memory HTTP requests; peak active requests 8 with configured limit 8. No sockets or public traffic.
- PostgreSQL + SQLite catalog/distributed checks: **34 passed, 2 skipped**, 9.91 s.
- First expanded full regression: **527 passed, 2 skipped, 1 warning**, 174.39 s, exit 0.
- Additional owner controls, interruption, duplicate execution, cancellation, pagination Retry-After and fairness/quota tests: **46 passed**, 26.36 s. Subsequent final review improved checkpoint payload recovery and expired-ACK handling; final verification is recorded below after execution.
- Existing Starlette/httpx TestClient deprecation warning remains. PostgreSQL-only skips in SQLite variants are intentional; PG variants execute using a local isolated non-superuser test role. Genuine schema v1/v5 migration fixtures preserve encrypted data and historical references. Existing browser/API regression tests use the authorized local application test portal, not real employer endpoints.

## Boundaries and remaining work

Shared source network/facts/failure state are coordinated; per-user subscription tasks remain. Some sync SQLAlchemy work remains inside discovery service coroutines. PostgreSQL admission rows serialize short critical sections and must be profiled before higher request rates. Workday offsets are not snapshot tokens and can shift; rolling replay is conservative, not perfect snapshot isolation. SmartRecruiters complete-board pagination remains bounded as before. The existing adaptive global task capacity still reduces after many observed errors. A publisher scan over its lease is rejected rather than renewed. LLM caps count requests, not provider-specific tokens/currency. Redis hints can fail without losing PostgreSQL tasks. No thousands-user, 1,000-live-source, cloud HA, network-partition or sustained soak performance claim is made. Production migration and physical backup restoration are still operator work, following the runbooks.

## Phase 5 final execution evidence

- Expanded full backend regression: **531 passed, 2 skipped, 1 warning in 172.55 s**, exit 0. Evidence: `artifacts/phase5-backend-tests.xml`. This run began before the final expired-ACK/dead-letter and pending-page recovery refinements.
- Final-head acceptance run covering distributed discovery, queue/worker reliability and owner controls: **50 passed in 35.05 s**, exit 0. Evidence: `artifacts/phase5-acceptance-tests.xml`. Includes those final refinements and two 1,000-source durable scheduling variants (SQLite/PostgreSQL), plus 1,000 parsed fixture feeds/2,000 HTTP responses with a measured peak of 8 active fixture requests. Fixture elapsed 0.862 s excludes real networking and is not a capacity result; retained in `artifacts/phase5-discovery-fixtures.json`.
- Final Ruff check (`cd backend && .venv/bin/ruff check app tests`) and `git diff --check`: passed. No frontend source changes; no frontend build/browser layout run in this phase. Existing backend end-to-end browser regression tests did execute against the authorized local test portal.
- No live source discovery was run in Phase 5; existing connectors were regression-tested against controlled responses. No claims of new live integration verification, production migrations, HA deployment or independently measured production-scale throughput.

Implementation milestone committed as `d9b7d51`. Verification/operations evidence is committed separately. Unrelated pre-existing manifests, screenshots and historical artifacts were left untouched by these commits.

# Phase 6 — premium product frontend

Implemented in local commit `17a8934`; locally verified. Full source/coverage details: [PHASE6_UI_IMPLEMENTATION.md](PHASE6_UI_IMPLEMENTATION.md). Retained backend APIs, approval security, encrypted data and all existing feature routes. No data migration or hosting.

Routed feature modules, semantic light/dark design system, responsive shell, compact cursor explorer/drawers, command search, applied filters, actionable overview and lazy feature views replace the monolithic page. Account/session-scoped query caching, selective invalidation and coalesced events replace redundant polling. Historical admin/provider responses retain explicit compatibility types.

Executed: frontend lint/typecheck/build/format, five cache/transport tests and OpenAPI drift check; 20 offline product checks; six adapted original studio regressions; 11 axe screen/theme evaluations without serious/critical violations; desktop/mobile widths 320–1920px and coarse-pointer touch. Actual PDF generation/download, draft application queuing, real source create/delete, dirty-form retention and same-tab account switching were exercised. Visibility events were simulated explicitly in headless Chromium.

Compared same synthetic explorer fixtures: 10 → 0 idle requests/17s; row 147.42 → 121.44px; decoded JS 599,856 → 547,323 bytes; encoded JS 171,114 → 168,094 bytes. Production workspace First Load JS 170 → 155kB. Single-run localhost observations are not field performance certification. Backend regression before Phase 7: 513 passed, 2 PG-only skips, one warning. No production deployment, real external applications/emails, live provider testing or screen-reader certification.

# Phase 7 — production readiness verification

Completed local implementation/review on 2026-10-28–29 UTC. Security milestone: `d497bcf`. Detailed evidence, rollout/rollback instructions, remaining blockers and reproduction commands: [SECURITY_REVIEW.md](SECURITY_REVIEW.md) and [PERFORMANCE_REPORT.md](PERFORMANCE_REPORT.md).

## Corrections

- Shared atomic five-minute authentication budgets with a global cardinality/work cap, pruning, fail-closed outages and a reusable dummy password hash. Short authentication transactions release connections before endpoint work; owner reauthentication admission precedes account locks to preserve SQLite compatibility.
- Recipient-specific Gmail follow-up checks require the parent receipt and complete bounded thread evidence, inspect replies after message 100, and stop on unknown/error/opt-out before any send checkpoint. No live mail sent.
- Private IPv6 and IPv4-mapped private literals now fail syntax-only discovery URL checks; three reproduced counterexamples added to regression coverage. Direct DNS checks remain, with socket-boundary rebinding protection still an open gate.
- Killable credential-stripped parser children with wall/concurrency/resource limits; request body deadlines/one bounded buffer; production origin checks independent of caller Host; malformed Unicode CSRF returns 403.
- Updated four vulnerable dependency pins; Docker consumes the audited lock. CI audits dependencies, verifies contract drift, provisions a disposable non-superuser PostgreSQL database, runs isolated regressions and retains reports. Hosted Actions/image builds were not executed.
- Streaming backup hard timeout plus error/cancellation child cleanup; real pg_dump/decrypt/pg_restore drill with preserved ciphertext/document/application references and tamper rejection.
- Catalog membership union avoids ordinary per-record canonical resolution; canonical-only pages skip eager joins; partial unprojected-row index; invalidated index-build connection cleanup. Schema remains v7, no columns/user data removed. Run the existing online index command for deployed databases.

## Executed final evidence

- **556 backend tests passed, 2 skipped, one deprecation warning in 185.57s**, exit 0. Includes 28 PostgreSQL variants; the two skips are SQLite variants of PostgreSQL-only tests. `artifacts/phase7-final-backend.xml` / `.json`.
- Frontend lint/types/build/format, five transport/cache tests and API type drift: passed. Phase 7 production browser rerun: **20 checks**, 11 axe screen/theme evaluations with no serious/critical findings. Actual local PDF, saved state, draft queuing, source create/delete, dirty forms and account switching exercised.
- Real local restore: 59,446-byte encrypted dump, 0.16s backup and 0.99s restore+verification (small fixture only). Tamper cleanup and paused workers verified. Separate local CI provisioning helper and final benchmark-harness smoke passed.
- Zero currently reported Python lock/npm advisories after updates; pip check, Ruff, Python compilation, YAML parsing and diff whitespace checks passed. Reports retained under `artifacts/phase7-*`.
- Reproducible PostgreSQL/HTTP smoke: 10k/10 clients p95 **398.6ms**, 100k/25 clients **1,975.2ms**, 1M/25 clients **11,735.9ms**; zero observed request errors. Rates 32.80/18.98/3.12 requests/s. Compact synthetic fixtures; not production acceptance/soak.
- Same-schema seven-sample query medians: 100k **89.73→62.44ms**, 1M **637.07→481.32ms**; 10k effectively unchanged. Rejected OR rewrite and its regression evidence retained. The aborted intermediate 1M attempt is not a completed benchmark.
- Each latest size completed 1,000 unique read-task claims with four workers, one expired-lease recovery and zero final backlog. Queue-only throughput 126–144 claims/s; no crawler throughput claim.

## Verdict and remaining gates

Locally verified for controlled evaluation, **not ready for unrestricted multi-tenant production or the requested scale**. Highest-priority work: socket/proxy DNS-rebinding boundary and independent runner privileges; large-catalog/read contention and versioned matches/summaries; per-user expensive-work/SSE/storage quotas; durable event replay/shared source fanout; full-size offsite/PITR restore and provider-receipt reconciliation; deployed TLS/monitoring and sustained mixed-load validation. No public load, real external submissions/emails, production migrations, hosting or HA claim.

Existing schema/IDs/tenant boundaries and workflows were preserved. Unrelated pre-existing manifests, screenshots and historical artifacts remain outside these milestone commits.

# Phase 8 — deployment and portfolio release candidate

Implemented README/DEPLOYMENT/PORTFOLIO/THIRD_PARTY_NOTICES, staged production worker profiles and resource/log controls, local worker heartbeat health, startup verification, version-pinned combined image, source-only manifest-verified packaging and manual release-candidate CI. Detailed release status: [PHASE8_RELEASE.md](PHASE8_RELEASE.md).

Fresh Linux source install (new venv/node_modules) passed dependency installation/checks, frontend lint/types/format/build/five tests/API drift, 532 backend tests with two SQLite-only skips and 20 browser checks. Local/cloud Compose validation and real local startup checks passed. No new benchmark, public source load or external action claim. Docker image/Windows/cloud gates remain unexecuted: vfs disk headroom ~0.5GB, no cloud credentials, unresolved public license and Phase 7 production boundaries. The candidate archive excludes runtime data and old manifests; existing unrelated dirty artifacts remain untouched.

# Phase 9 — public preview launch

Public introduction/demo deployed using Sites at **https://internpilot-ai-notebook.antigravityfree101.chatgpt.site**. Version 3 reached terminal `succeeded`; independent unauthenticated TLS-verified HTTP checks passed for pages/assets and all 11 initial JS/CSS hashes matched the tested export. [Full launch evidence, deployment IDs, reproduction/rollback, top-15 critical review](PHASE9_LAUNCH.md). [Bio/caption and recruiter description](LAUNCH_MATERIALS.md).

Implemented original public identity/landing, read-only synthetic interactive demo, policy/contact routes, social/icons, scoped private providers, explicit login/register routing, legacy view redirects, unknown-route 404, accessible lazy demo detail, theme contrast fixes, Docker static assets/build configuration and exact-export/live QA scripts. No data/schema/backend behavior changes or external applications/emails. Static allowlisting deliberately excludes account/API/worker capabilities; full backend remains undeployed and not approved for unrestricted production.

Executed: **533 backend tests passed, 2 SQLite skips**, one existing warning; frontend build/types/lint/format/OpenAPI drift and five unit tests; **9 public** grouped browser checks with 10 zero-violation axe route/theme evaluations; **20 private** workflow checks with 11 axe evaluations; three exact-static browser groups. Final local mobile Lighthouse 98/100/100/100, LCP 1.92s, TBT 128ms, CLS 0 with gzip; pre-split uncompressed result retained and not treated as an apples-to-apples performance comparison. Preceding compressed run was 97, with normal single-run variation. New release-boundary test rerun passed; both Compose configurations validated. Public dependency notices now accompany the bundles. CI includes public/private browser and static-export jobs; hosted execution is unverified.

Limitations: live browser blocked by managed proxy CA; automatic approval review rejected persistent trust-store modification, left unchanged with user question pending. No real-device Instagram, field CWV, cloud backend, new PG/live-provider certification, new image build or post-change fresh OS install. Private route/form CLS can exceed 0.1. Phase 7 egress/runner/quotas/capacity gates and operator contact/license/restore review remain explicit. Unrelated preexisting manifests, screenshots and historical artifacts remain outside Phase 9 commits.

Source milestone: `fffe0e8` (public product routes and preserved workspace flows). Release validation/notices/docs follow as a separate milestone. Regenerated the 305-file source-only archive with CRC and per-file SHA-256 verification; external digest/report retained. No GitHub push, full backend deployment or hosted CI success is claimed.

# Terms motion and invitation-only accounts

2026-10-29 follow-up: retained public landing/demo; redesigned Terms with section navigation, fluid movement and reduced-motion handling. Corrected an intermittent dark-mode contrast failure by removing text opacity fades. Published version 5 and verified public pages/assets over HTTPS. The public `/login` entry discloses the undeployed account backend and collects no credentials.

Implemented actual owner-issued, email-bound, single-use, expiring/revocable invitations in the full app. Owner UI requires current password and explicit consent; recipients choose their own password. Server-enforced `INVITATION_ONLY=true` is the default and mandatory in production. Legacy shared codes cannot bypass it. Consumption/account/session creation are transactional, with concurrency/rollback tests; stored emails are encrypted and bearer tokens are hashed. Reused the existing coordination namespace without a schema migration. Existing users/IDs/data remain intact; existing access can be revoked through the existing owner account controls.

Evidence: targeted **44 passed**; full SQLite **538 passed, 2 PostgreSQL-only skips**, one existing warning; five browser workflow groups, four Terms/login axe evaluations with zero violations, four exact-static export groups, frontend build/types/lint/format/five tests/OpenAPI drift, backend Ruff and Compose/CI parsing passed. No external email, real application or cloud backend deployment. The initial opacity-motion contrast run failed and was corrected before the final passing browser run. Hosted CI and new PostgreSQL variants were not executed. [Setup, rollout/rollback, deployment IDs, tests and limitations](ACCESS_CONTROL.md).
