# Existing-project upgrade

Updated in place on 21 October 2026. Next.js, React, FastAPI, SQLAlchemy, PostgreSQL/SQLite, encrypted documents and the existing Playwright workflow were preserved. No repository was created, no Git changes were committed, and no service was deployed.

## What works now

| Improvement | Result |
| --- | --- |
| Unified opportunity discovery | Internship and hackathon records share provenance, matching, search, bookmarks and application status. New accounts receive the existing ATS sources plus MLH and the published InternScan India feed. Existing accounts receive missing new sources through an additive migration. |
| JobSpy interoperability | Import authorized CSV/JSON/JSONL exports through Discovery sources. An optional `jobspy_feed` reads a permitted public export URL. Files are bounded to 8 MiB / 2,000 records, non-internships are skipped, invalid/private/restricted destinations are rejected, and metadata is labeled unverified. No JobSpy network scraper or board-login automation is installed. |
| Hackathon discovery | MLH event listings, permitted RSS/Atom announcements and schema.org Event/Hackathon pages are supported. Registration availability stays unknown until actually confirmed; an event's start date is never substituted for its registration deadline. |
| Explainable matching | Separate internship and participation logic, strict graduation bounds, verified skill comparison, missing skills, explicit eligibility concerns, deadline urgency, role preferences, hackathon interests and recommended next actions. Location and remote metadata cannot prove international eligibility. |
| Better automation | Deadline-priority queue, bounded concurrency, per-source refresh/backoff, validators, incremental source inventories, account-isolated deduplication, worker heartbeats and opt-in automatic PDF preparation with daily budgets. Automatic drafting stops for review before browser upload. |
| Reliable state | Saved opportunities survive source removal. Stronger employer facts and verification timestamps survive weaker aggregator updates. Saved deadline/closure/compensation changes generate deduplicated in-app notices. Expired records leave the default explorer. |
| Notifications | High-match alerts, deadline reminders and application updates; browser notices while the workspace is open; configurable email, Telegram and authorized Twilio WhatsApp providers. External messages become encrypted drafts and require approval of the specific body and destination. Quiet hours defer rather than silently send later. |
| Application review | Factual, versioned PDFs, missing-field checklist, unresolved-question visibility, exact document/profile/listing upload consent and conservative crash checkpoints. A changed profile invalidates old approval. A worker lost after an upload or send checkpoint pauses for reconciliation. |
| Interface | Dedicated internship/hackathon/recommendation/saved views, search and filters, 20-item pagination, paid/prize filtering that excludes unknown and zero compensation, saved details, real source/worker health, notification review, persistent system/light/dark themes and responsive mobile navigation. |
| Account security | Password rotation revokes old sessions and renews the current browser session; other-session revocation and a hidden-input local recovery CLI. Secrets remain server-side. |
| Engineering | Schema version 3, additive migration tests, Ruff and ESLint correctness checks, pinned dependency lockfiles, PostCSS security override, isolated browser-test runner and safe source packaging. |

## Verification executed

- **364 backend tests passed** in 127.05 seconds. This includes real API processes, local Playwright form filling/upload/receipt checks, account isolation, import formats, duplicates, timezone boundaries, source outages, consent invalidation, notification provider mocks and worker recovery.
- **20 browser acceptance checks passed** against a fresh SQLite database and production frontend: registration, profile verification, local test submission and receipt, download, UI import and repeated import, search/pagination/bookmarks, persisted theme/saved items, explorer views, quiet hours, password/session rotation, read-only real discovery, truthful metrics, details and mobile navigation at 390 px. No unhandled page errors or horizontal mobile overflow were observed.
- **PostgreSQL migration tested:** a local synthetic version-1 database migrated to versions 1/2/3, the second migration run made no duplicate changes, encrypted profiles/documents survived, TLS certificate/hostname verification remained enabled, and a new process reopened it successfully. See [upgrade-postgres.json](../artifacts/upgrade-postgres.json).
- Frontend lint, TypeScript and optimized Next.js build passed. `npm audit` reported **zero known vulnerabilities** after replacing Next's vulnerable PostCSS dependency with a compatible patched 8.5.x release. `pip check` and backend Ruff passed. This is not a comprehensive security certification.
- No real application was submitted, no personal document was uploaded externally, no provider message was sent, and no hosting occurred during verification. Notification calls were mocked at the SMTP/HTTP boundary; this does not establish live delivery.

Machine-readable evidence: [backend JUnit](../artifacts/improvements-backend-tests.xml), [browser report](../artifacts/ui-acceptance.json), [PostgreSQL report](../artifacts/upgrade-postgres.json).

## Sources and limits

| Source | Evidence / limitation |
| --- | --- |
| Greenhouse/Figma, Lever/Palantir, Ashby/Ramp | Existing read-only live validation captured 11 / 42 / 6 internships. The upgraded browser run also retrieved real public listings. Counts change over time; neither result guarantees India/2029 eligibility. |
| MLH | Live scan captured 68 upcoming non-cancelled event announcements. Dates and organizer metadata are retained. Registration and international participation still need verification. |
| InternScan India | Live published API returned 12 internship references. Feed refresh defaults to 15 minutes; upstream workflow publishes daily. References cannot overwrite independently verified employer facts. |
| SimplifyJobs | 1,763 public listing references parsed. Bounded employer-page sampling is explicitly partial; sampled links did not establish verified JobPosting metadata. No bulk source-code/data reuse. |
| RSS/Atom and structured pages | Fixture-tested generic connectors for explicitly permitted sources, including hackathon announcements and events. This does not certify every university or hackathon site. |
| SmartRecruiters / Workday | Connector implementations and fixtures exist; no new live employer-board verification was performed in this upgrade. Workday listing-only metadata remains insufficient for verified eligibility. |
| Devpost / Devfolio / Unstop / HackerEarth / DoraHacks | No certified direct integrations were fabricated. Generic permitted feeds/pages may be configured when available. Devpost direct integration fails closed until an approved method is established. |
| LinkedIn / Indeed / Wellfound / Internshala | Direct crawling and authenticated scraping are disabled. Restricted links are skipped by the importer. Use official employer links or an independently authorized integration. |
| External application submission | Manual final completion. The only certified final-submit adapter is the isolated local test portal. Mode `auto` means policy-controlled drafting in this release; it does not override per-action upload/message consent. |

Source evidence: [MLH/Simplify validation](research/source-validation.md), [InternScan validation](research/aggregation-validation.json). The [five new repository audits](research/combined-repositories.md) record inspected revisions, implementation evidence, licenses and reuse decisions; the original six are recorded in [the upgrade plan](UPGRADE_PLAN.md) and its linked audits.

## Configure and run

Use the existing [Windows/local setup](../README.md). No paid API or GPU is required for public feeds, deterministic matching or PDF generation. Existing installations should back up their database and encryption key, then restart API and worker with the updated source; migration 3 runs automatically. Preserve the original encryption key.

In the UI, verify profile facts, review sources, save notification preferences and opt into automatic drafting only if desired. A source's `permitted` flag attests read-only access; it grants no permission to submit applications.

Optional server-side credentials:

- Email: `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM`, optional `SMTP_USER` / `SMTP_PASSWORD`; verified STARTTLS or port-465 TLS is required.
- Telegram: `TELEGRAM_BOT_TOKEN`; supply your authorized chat ID in the private notification settings.
- WhatsApp: authorized Twilio `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`; provider/sandbox recipient rules still apply.
- Advisory AI: `LLM_PROVIDER=openai_compatible`, `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`. Only public descriptions are sent, after deterministic exclusions.
- Optional search: `BRAVE_SEARCH_API_KEY` and a permitted search source.

Provider variables are wired into both Compose API and worker environments. Empty variables disable the channel. No credentials are bundled.

To repeat verification:

```bash
cd backend
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/ruff check app tests
.venv/bin/python -m pytest -q
cd ../frontend
npm ci
npm run lint && npm run typecheck && npm run build
cd ..
backend/.venv/bin/python scripts/run-ui-acceptance.py
```

On Windows use `backend\.venv\Scripts\python.exe`; the browser runner needs ports 3000/8000 free and a built frontend. It creates and removes its own temporary database and never loads the user's `.env`. Docker Desktop/PowerShell end-to-end execution was not available on this Linux workspace.

## Remaining work requiring independent access or certification

Live notification credentials/delivery testing, approved adapters for individual external employers, mailbox confirmation ingestion, OCR for image-only resumes, browser handoff for interactive/login-heavy forms, and platform-specific licensed APIs remain outside verified support. There is no CAPTCHA/MFA bypass, guarantee of internet-wide coverage, or assertion that an unverified reference is open. External browser preparation is conservative static-form inspection with screenshots; users complete unsupported or interactive forms on the official website.

The final data-quality checks also prove that stale aggregator references cannot keep a posting open after a complete official employer scan removes it. Dark-theme secondary labels and primary controls were adjusted for stronger contrast after inspecting the actual mobile and desktop screenshots.

The updated Compose configuration was validated without starting services. The full current image set was not rebuilt in this final pass; earlier full-stack Docker evidence is historical, while the current API/browser runs and PostgreSQL migration were verified separately.
