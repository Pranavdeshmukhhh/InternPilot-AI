# Executed verification

The current upgrade passed **364 backend tests** and **20 browser checks**. Frontend lint/typecheck/build and backend Ruff/pip consistency checks passed. The production dependency audit returned zero known vulnerabilities. A local PostgreSQL version-1 database migrated to version 3, preserved encrypted records, and reopened from a new process over verified TLS. No external submission, personal-document upload or provider message was sent.

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
