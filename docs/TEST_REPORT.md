# Executed verification

## Studio interface — 28 October 2026

**67 browser checks passed on the final production build**: six studio interface checks, 15 browsing/theme checks, seven regional checks, five source-review checks, 24 existing acceptance checks and ten production workflow checks. Production compilation, lint/type checks and script Ruff passed. Backend code/schema did not change, so the 489-test backend result below remains dated evidence from 27 October rather than a claimed rerun.

New checks exercise compact rows, usable search positioning, separate bookmark actions, a full-height opportunity sheet, evidence visibility, keyboard containment, Escape, return focus and fitting picker labels at mobile widths. Desktop/mobile/light/dark screenshots were inspected. Existing regression checks covered profile verification, filters, saved opportunities, hackathons, provider-disabled outreach, owner step-up access, account isolation, document downloads and confirmed submissions to the isolated local fixture. Browser navigation waits for the new closing-sheet animation to finish; no test timeout was increased. [Studio results](../artifacts/studio-ui.json) · [Design and previews](STUDIO_INTERFACE.md).

The studio suite uses six labeled fictional opportunities, which do not inflate real dashboard metrics. Existing acceptance separately ingested 46 real public-source records; this does not establish current eligibility or availability. No real external application or recruiter email was sent. No new dependency, provider credential, deployment or database migration was introduced.

## Warm UI and query work — 27 October 2026

The complete backend suite passed **489 tests**, zero failures/errors/skips, in **162.43 seconds**. The new 15-check browser suite passed against an isolated temporary database, covering light-first appearance under an OS dark preference, explicit theme persistence, text/action contrast, curved panels, keyboard focus/shortcut, remembered filters, pagination, cancellation, stale-response rejection, actual 503/retry recovery, mobile widths, reduced motion, event coalescing, simulated hidden-tab lifecycle and account isolation. Frontend production build/type/lint checks, Ruff and Python dependency consistency passed. [Current JUnit](../artifacts/warm-query-backend-tests.xml) · [New browser results](../artifacts/warm-ui.json) · [Changes and limits](WARM_UI_AND_QUERY_UPGRADE.md).

The local SQLite benchmark created 10,000 synthetic opportunities and returned a 20-item newest-first page in **0.470546 seconds**, with **20 matching evaluations and 20 ORM hydrations**. Candidate facts were scanned in batches of 200 to preserve exact filters/totals. This is neither indexed-only SQL pagination nor a cloud-throughput/best-match benchmark. New query tests cover Unicode casefolding, literal wildcard searches, missing/null field separators, malformed remote values, deadlines/timezones, strict qualifications, saved orphans and ownership. PostgreSQL queries were compiled; live execution of this new query path was not performed. Schema version 5 remains unchanged. [Benchmark evidence](../artifacts/warm-query-benchmark.json).

In total **61 browser checks passed**: the 15 new checks, 24 existing acceptance workflows, seven regional checks, five source-review checks and ten production workflows. The production regression caught a stale Resume studio snapshot after worker completion; opening the view now fetches its current document list, and the original download assertion passes unchanged. Production, warm and source review reran after that fix; regional/existing checks passed immediately before that small navigation-hook correction. No test timeout was extended to mask the issue. Existing acceptance also ingested 56 records from real public sources; those counts are not eligibility or availability guarantees.

Measured browser contrast ratios were 13.52:1 for light body text, 6.35:1 for the light primary button, 14.35:1 for dark body text and 8.41:1 for the dark primary button. These specific checks do not certify every possible component against all accessibility standards. Browser fixtures are clearly synthetic; no real source scan, recruiter email, external application or external document upload occurred in the new suite. Existing dependency/build deprecation notices remain.

## Small-employer discovery — 26 October 2026

The complete backend suite passed **482 tests**, zero failures/errors/skips, in **118.18 seconds**. Five new source-review browser checks and seven regional checks passed against isolated temporary databases. The frontend production build (including lint/type checks), Ruff and Python dependency consistency passed. The existing broader browser suites were not rerun in this turn. [Current JUnit](../artifacts/small-employer-backend-tests.xml) · [Source review browser results](../artifacts/source-discovery-ui.json) · [Regional results](../artifacts/regional-ui.json) · [Behavior and activation](SMALL_EMPLOYER_DISCOVERY.md).

New tests cover bounded diverse queries, employer-link extraction, known ATS slugs, source proposal deduplication/ownership/permission, SSRF/restricted destination rejection, persistent dismissals, restart/304 handling, alternate role uncertainty, snippet provenance, preservation of verified employer data and fair due-source scheduling. The root/container environment cannot launch sandboxed Chromium; the static external-form branch test uses a local-only fixture launch wrapper, while a separate test confirms sandbox failures stop production preparation. No production security fallback was added. An initial run failed this environment-dependent fixture; the final complete run passed after the test-only correction. A Starlette/httpx deprecation warning remains; no extra runtime dependency was added solely to suppress it.

A live read-only Sarvam AI careers-page scan found two publisher-metadata-backed marketing internships in Bengaluru and a linked Ashby board. This is not a claim of technical-role availability, small-employer identity, Nagpur/Pune vacancies or undergraduate eligibility. Authenticated Brave responses were mocked because no key was configured. The updated scheduler passed SQLite tests; its PostgreSQL execution/throughput was not rerun. No source was enabled in a real account, and no external application/email/document upload occurred. [Live publisher evidence](../artifacts/employer-discovery-live.json).

## Previous production upgrade

The previous production upgrade passed **434 backend tests**, zero failures/errors/skips, in **156.85 seconds** (JUnit suite time: 156.750 seconds). **41 browser checks** passed across 24 existing workflows, seven regional checks and ten production-upgrade checks. Frontend lint/typecheck/optimized build, backend/script Ruff and pip dependency consistency passed. At that time, `npm audit --omit=dev` returned zero known production dependency vulnerabilities. [Previous JUnit](../artifacts/production-backend-tests.xml) · [Previous browser suite](../artifacts/production-ui.json) · [Setup and limitations](PRODUCTION_UPGRADE.md).

Actual PostgreSQL verification migrated a synthetic version-4 database to version 5 twice, preserved its encrypted profile, scheduled 1,000 jobs, and completed 1,000 unique claims across eight concurrent threads. Shared host-budget reservation was verified. Scheduling took 2.3818 seconds and claiming/completing 4.6970 seconds. This local database test made no HTTP requests/browser launches; production TLS and high-scale HTTP throughput were not tested. [PostgreSQL report](../artifacts/production-postgres.json).

Live read-only checks returned Figma 10, Palantir 46, Ramp 6, MLH 70, InternScan India 11 and Sarvam AI 3 records. These are source snapshots, not India/2029 eligibility or open-registration guarantees. Sarvam's observed records were marketing internships, not claimed AI engineering roles. [Source evidence](../artifacts/production-live-sources.json).

Gmail OAuth/exchange/refresh, exact-preview approvals, send receipts, reply/DSN processing and failures used mocked provider responses; no live sender was connected or external email/application sent. The authorized local browser demonstration did fill fields, upload a PDF and obtain a synthetic portal receipt. Backups passed streaming roundtrip, wrong-key and tamper checks; a live cloud restore was not performed. Both Compose configurations validated. New Docker images were not rebuilt in this workspace, which had under 1 GB free disk; cloud HTTPS provisioning and Windows execution were not tested.

The following upgrade notes are historical evidence retained for comparison.

The regional discovery upgrade on 23 October 2026 passed **397 backend tests** in 120.40 seconds and **31 browser checks** (24 existing workflows plus seven regional checks). Frontend lint/typecheck/build and backend/script Ruff checks passed. The regional browser run used a fresh temporary database, exercised both opportunity types and persisted city preferences, and captured desktop/mobile screenshots. See [regional backend JUnit](../artifacts/regional-backend-tests.xml), [regional browser results](../artifacts/regional-ui.json), and [live regional source checks](../artifacts/regional-live-sources.json). No real external application, personal-document upload or provider message was sent. Authenticated Brave Search was tested with synthetic responses; live access requires a server key and was not exercised.

The preceding owner upgrade passed 373 backend tests and 24 browser checks. Its pip consistency check, dependency audit with zero known vulnerabilities, and PostgreSQL migration from version 1 to version 4 over verified TLS are historical evidence; these dependency/database checks were not rerun for the regional change, which adds no dependencies or schema migration.

See [the current upgrade report](UPGRADE_REPORT.md), [backend JUnit](../artifacts/improvements-backend-tests.xml), [browser results](../artifacts/ui-acceptance.json) and [PostgreSQL results](../artifacts/upgrade-postgres.json). Notification tests use mocked providers; no live delivery is claimed. Windows helper scripts are provided but were not executed on Windows in this Linux workspace.

The following section records the earlier 167-test baseline and its original live snapshot; it is retained as historical evidence.

# Original baseline verification

InternPilot AI was implemented and checked in a managed Linux environment with Python 3.12, Node.js, Chromium, Docker, PostgreSQL 16 and Redis 7. Discovery requests were read-only. **No real employer application was submitted.** All submission tests used the explicitly enabled local test portal and synthetic candidates.

## Automated backend suite

The complete suite passed: **167 tests, 0 failures, 0 errors, 0 skipped, in 80.838 seconds**. See [the machine-readable summary](../artifacts/backend-test-summary.json) and [JUnit results](../artifacts/backend-tests.xml).

| Area | Passing cases |
| --- | ---: |
| API, authentication, encrypted storage and worker integration | 7 |
| Real Playwright form and upload workflows | 14 |
| Discovery connectors, caching and permitted access | 27 |
| Resume parsing and factual PDF generation | 16 |
| Optional structured LLM analysis | 19 |
| Eligibility, exclusions, mandatory requirements and preference ranking | 72 |
| Service ownership, freshness, retry and restart guards | 12 |

After shortening an oversized generated test parameter label, the 16 document tests passed again. `pip check` found no broken dependencies. Application behavior was unchanged by that test-label edit.

## Acceptance evidence

| Requested behavior | Executed result |
| --- | --- |
| Discover real internships | Public Greenhouse/Figma, Lever/Palantir and Ashby/Ramp endpoints returned 11, 42 and 6 relevant listings respectively: **59 total**. |
| Extract actual requirements | Public descriptions, source URLs and exact requirement quotations are retained in the captured snapshot. Unknown requirements remain uncertain. |
| Reject incompatible graduation years | The India/2029 profile rejected **34** captured listings and held **25** for review. A real Palantir posting states, “Must be planning on graduating in 2028.” A 2029 candidate is rejected. |
| Rank matching opportunities | Deterministic 0–100 scoring, skill overlap, publication/deadline priority and editable preferences were exercised. Eligibility remains a separate decision. |
| Produce accurate tailored resumes | Actual PDF generation and text extraction proved that verified facts survive export and unverified achievements, phone numbers and qualifications are omitted. Cover letters and PDF/DOCX/TXT imports were tested. |
| Fill a supported application and upload a document | Real Chromium filled the local form, selected India and 2029, and uploaded a generated PDF. |
| Submit to an authorized test endpoint | Real HTTP form submission reached only the local test portal. A screenshot was encrypted and committed before the final click. |
| Detect confirmation | The worker checked the confirmation identifier and independently retrieved a receipt whose SHA-256 matched the uploaded PDF. Missing or mismatched receipts became uncertain. |
| Prevent duplicate submissions | API/database uniqueness, the portal's idempotency key and repeated UI actions prevented duplicates. Separate accounts received separate synthetic identities and receipts. |
| Recover after a worker restart | Tests abruptly killed real worker processes before and after the final checkpoint. Safe preparation resumed; possible submissions became uncertain and were never automatically retried. |
| Handle corrected candidate facts | Restarted preparation generated a new PDF, retained the old version and invalidated old approval when the candidate corrected facts. |
| Pause for intervention | CAPTCHA, sensitive visa questions, missing verified answers, unsupported forms, sandbox failure and emergency stop all paused work. |
| Preserve source freshness accurately | Removed listings became inactive. Later HTTP 304 responses refreshed active listings without reviving removed postings. Partial scans did not imply complete coverage. |
| Respect retries and account boundaries | Retry-After seconds/dates were honored. An account's configured source could not overwrite another account's imported job data. Stale workers could not overwrite newer results. |

The live discovery capture was made on **2026-10-20 at 16:57 UTC**. It is historical evidence, not a claim that every listing remains open. See [discovery evidence](../artifacts/live-discovery.json), [full public snapshot](../artifacts/live-listings.json), [rejections](../artifacts/live-rejections.json), and [offline replay](../artifacts/offline-replay.json). The replay re-extracts and ranks the stored descriptions without making any application.

## Frontend and connected browser verification

The final frontend passed TypeScript checks and a full Next.js 15.5.28 production build, including the latest CSS changes. See [build evidence](../artifacts/frontend-build.json).

All **13 connected browser checks passed**, with no unhandled browser runtime errors. The production frontend completed registration, profile verification and persistence, policy updates, source health, a confirmed local browser submission, repeat-action duplicate prevention, protected download, real public discovery of **59 listings**, truthful real submission metrics, opportunity details and responsive mobile navigation without horizontal overflow.

See [UI acceptance evidence](../artifacts/ui-acceptance.json), [desktop screenshot](../artifacts/dashboard-desktop.png) and [mobile screenshot](../artifacts/dashboard-mobile.png). The retained runner is `scripts/ui_acceptance.py`; it uses synthetic data and refuses a backend without test mode.

## Docker and PostgreSQL

All five services—frontend, API, worker, PostgreSQL and Redis—were observed healthy. Authenticated dashboard and opportunity endpoints returned actual JSON successfully against PostgreSQL. The local demo verified PDF upload bytes, screenshot bytes, confirmation, duplicate prevention, unchanged master profile and exclusion of synthetic submissions from real metrics. See [Docker evidence](../artifacts/docker-validation.json) and [final demo artifacts](../artifacts/docker-local-demo-final).

PostgreSQL also passed schema initialization, the candidate/opportunity unique constraint, safe lease recovery, uncertain post-checkpoint recovery and **six unique parallel queue claims**. See [queue evidence](../artifacts/docker-postgres-queue.json).

The managed Docker VFS storage driver exhausted this workspace's disk during a final image rebuild. Existing built images were retained; the final backend source was additionally validated through a read-only source snapshot in the running containers. The latest frontend source was built and served natively for connected browser QA. This distinguishes the final-source runtime check from a fresh rebuild of every image. The shipping Dockerfiles and Compose configuration are included.

This environment also required a read-only trusted CA bundle for outbound HTTPS from containers. Validation preserved the proxy path and TLS verification; a public Greenhouse API request then returned HTTP 200. The environment-specific override and certificate files are not part of the delivered project. Normal desktop setup uses system/public trust. See [operations](operations.md).

## Verification limits

- **External final submissions remain unsupported by the shipped adapters.** Only the authorized local portal can perform an automated final click. External static preparation is tested with controlled fixtures; real employer submissions require manual completion or a separately implemented, authorized adapter.
- Greenhouse, Lever and Ashby were checked live. Other connector paths use controlled API/feed fixtures; this report does not claim live access to every ATS or restricted job platform.
- The optional LLM provider was tested using structured HTTP fixtures. No paid live LLM request was required. LLM advice cannot create candidate facts or override deterministic rejection.
- Automatic email inbox ingestion and outbound email/SMS notifications are not configured. In-app notifications and manually reported application statuses work.
- Windows 11 PowerShell scripts are supplied, but a Windows/Docker Desktop acceptance run was not available here. Python helpers, shell syntax, dependency consistency and Compose configuration were checked on Linux.
- There was no independent penetration test or load test. Public/shared deployment needs the additional safeguards described in [security boundaries](security.md), including connect-time egress enforcement against DNS rebinding. External Chromium requires a working sandbox; failure pauses preparation.

Auto Apply and test mode are disabled by default. No secrets, real candidate records, browser sessions or runtime databases are included in the source package.

The latest owner/UI upgrade adds nine backend owner-access cases, four browser owner workflows, and a version-3-to-4 migration regression. Owner operations require role checks, CSRF, fresh password verification, a reason and action-specific consent; existing passwords and hashes are never returned. See [owner setup](OWNER_CONSOLE.md).
