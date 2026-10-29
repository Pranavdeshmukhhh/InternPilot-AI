# Phase 8 release report

Date: 2026-10-29 UTC. **Engineering release candidate, not a cloud deployment or unrestricted production release.** Existing functionality/data formats remain compatible; no database migration or real external submission/email was performed in this phase.

## Changes

- Replaced the historical narrative README with a current product/engineering overview, setup, architecture diagram, actual performance table, screenshots and explicit limitations.
- Added DEPLOYMENT.md for Windows 11/Docker, native Linux/WSL, staged cloud startup, migration/backup/rollback, costs and incident diagnostics; PORTFOLIO.md for schema/trade-offs, a ten-minute interview walkthrough and three evidence-backed resume bullets.
- Production Compose now requires explicit discovery/action profiles; default web-only startup does not start external workers. Added process/memory limits and rotating logs to cloud API/worker defaults; local worker now has its own heartbeat health check. The memory caps require aggregate host budgeting, not a guarantee that every role fits a small VM.
- Existing runtime configuration validation, secure cookies, private service networking, application approvals, structured worker logs, Automation/Owner diagnostics and PostgreSQL task authority are retained. Added a read-only startup verifier with explicit web-only mode. Cloud `/api/ready` intentionally requires a crawler heartbeat; use web-only checks until discovery is enabled.
- Existing CI covers PostgreSQL migration/concurrency/tenant tests, backend lint, frontend types/build, OpenAPI drift and Python/npm dependency scans. Added a manual release-candidate workflow that builds both images and archives source, with no automatic registry push or deployment. Hosted workflows were not executed.
- Frontend runtime recipes now retain discovered dependency LICENSE/COPYING/NOTICE files; these image changes remain unbuilt here. Both backend deployment Dockerfiles now use the audited version-pinned dependency closure. The source packager includes previously omitted frontend contract/test scripts and SQL fixtures; uses an allowlist, skips symlink redirection, scans private-key/GitHub-token signatures, checks every archive member against a SHA-256 manifest, atomically replaces the archive and writes an external checksum. It does not modify the older unrelated MANIFEST.sha256 or bundle old runtime artifacts.
- THIRD_PARTY_NOTICES records font obligations, upstream non-reuse decisions, dependency/container review scope and the absent project license. Clean installed-package metadata inventories cover 47 Python and 293 Node packages. UNKNOWN/composite licenses and OS/Chromium redistribution remain an operator/legal review, not blanket clearance.

## Executed checks

| Check | Actual result |
| --- | --- |
| Fresh source extraction and Linux dependency install | New directory/venv/node_modules under `/tmp`; exact Python lock and npm ci completed; pip check passed. No reuse of project venv/node_modules. System Python/Node/Chromium and OS libraries were already installed; this was not a fresh VM/Windows install. |
| Clean-install backend regressions | **532 passed, 2 skipped, one deprecation warning in 202.62s**, exit 0. SQLite fresh environment; PG-specific variants not enabled in this run. Phase 7 separately recorded 556 passed including 28 PG variants. Evidence: `artifacts/phase8-clean-backend.xml` / `.json`. |
| Clean frontend | Lint, typecheck, five transport/cache tests, generated API drift check, formatting and production build passed. Workspace First Load JS 155kB. Same existing Next ESLint plugin warning. |
| Fresh build browser flows | **20 checks passed**, 11 axe screen/theme evaluations without serious/critical violations; 320–1920px and touch/keyboard. Real local API writes/PDF generation/download/draft preparation/source create-delete exercised. Existing backend tests cover explicit approvals, local test-portal confirmation, status tracking and duplicate/recovery behavior. |
| Discovery | Actual parsers, normalization, eligibility and worker orchestration exercised in backend controlled fixtures, including source failures. No new live provider ingestion verification; synthetic UI rows are labeled. |
| Startup verification | Web `/`, `/api/health`, `/api/ready` passed against the fresh isolated local app. This is not an external HTTPS/worker-fleet readiness check. |
| Compose | Local and cloud configs parsed with Docker Compose 2.40.3, engine 28.4.0, synthetic environment only. No real DSN or expanded secrets printed. |
| Release archive | File-boundary unit test passed; generated archive CRC and per-file manifest verification passed. Scanner is limited, not exhaustive Git history secret scanning. |
| Source hygiene | Backend Ruff, Python compilation and whitespace checks passed. Original unrelated manifest/screenshots were preserved, not silently committed as release evidence. |

The clean-install archive predates final documentation and packaging-test additions; application source/dependency files are unchanged. New packaging/startup changes were checked separately. Native Windows, Docker image builds, cloud HTTPS and hosted CI have **not** been executed here.

## Exact remaining actions

1. **Build environment:** the accessible local Docker daemon uses vfs and writable disk has about 0.5GB free. Cached images already exceed that. Image builds were deliberately not started to avoid exhausting the environment. Provide several GB of build headroom (recommend at least 6–10GB), then run both Dockerfiles and the Compose clean-volume smoke on a disposable project. Never remove real volumes to make space.
2. **Cloud authorization:** runtime inspection found no configured cloud credentials/outbound identity. Supply a target VM/account and budget through a secret mechanism, managed PostgreSQL/TLS CA, DNS/domain, persistent keys and backup target. Follow DEPLOYMENT.md; no service URL, registry digest or deployment success is claimed.
3. **Public/source release:** owner selects a license and confirms rights to original contributions; review third-party/container notices, dependency UNKNOWN entries and Git history with a dedicated secret scanner. Do not call this open source before that decision. No private credentials or real candidate records were deliberately added; bounded scanners cannot prove absence of all secrets.
4. **Production gates:** enforce socket/proxy egress against rebinding/private networks, independent browser/parser privileges, quotas and bounded catalog/matching reads. Phase 7's 1M/25-client p95 was 11.74s. This release does not hide that behind new hosting configuration.
5. **Provider gates:** configure permitted search/Gmail/notification credentials server-side, verify OAuth consent/redirects, provider quotas and specific user approvals. Certify any new submission adapter independently; current external final submission remains manual.
6. **Promotion/recovery:** run full-size encrypted offsite restore with matching keys/artifacts and outbound receipt/suppression reconciliation; canary deployment and sustained mixed-load/SSE/failure tests. Add external uptime/backup-age/queue-age alerts to the operator's monitoring account.

## Deliverable

`dist/InternPilot-AI-release.zip` and `.zip.sha256` are generated local source artifacts. The zip has RELEASE_MANIFEST.json, source/configuration/tests/docs and selected synthetic screenshots/evidence. `artifacts/phase8-package.json` holds its current digest; rebuilding changes it. No remote repository was created, pushed or published. Resume bullets and project descriptions state demonstrated local achievements and preserve placeholders for unmeasured users, deployment latency and costs.
