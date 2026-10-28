# InternPilot AI

InternPilot discovers internships and hackathons, evaluates documented eligibility, prepares factual application documents, and runs guarded browser workflows. It is a local-first Next.js + FastAPI application with PostgreSQL, a durable worker queue, optional Redis events, and Playwright. It runs on Windows 11 through Docker Desktop; no NVIDIA GPU or paid LLM is needed.

The latest interface redesign uses neutral surfaces, larger system typography, compact opportunity rows, restrained blue controls and an edge-aligned detail sheet. Search/results take priority; discovery setup stays available through expandable sections. Keyboard focus, bookmarks, saved filters, light/dark preferences and the existing workflows are preserved. **67 browser checks and the production build/lint/type checks passed.** See [the studio interface and previews](docs/STUDIO_INTERFACE.md) and [executed verification](docs/TEST_REPORT.md).

The previous query upgrade passed 489 backend tests and added page-sized chronological scoring: a local 10,000-record synthetic benchmark returned a 20-item page in 0.470546 seconds. Exact totals still scan candidates; full matching still computes necessary scores. That backend implementation was unchanged during this interface redesign. See [query performance and limits](docs/WARM_UI_AND_QUERY_UPGRADE.md).

Discovery retains 20 default search lanes for local, India, remote and international opportunities, alternate student-role titles, startup/incubator/university discovery, a permission-based source-review queue, bounded publisher-link extraction and fair scheduling for low-volume sources. A prior live publisher-page check found two marketing internships and its linked ATS board; broader authenticated search still requires your API key. See [small-employer discovery and activation](docs/SMALL_EMPLOYER_DISCOVERY.md).

The existing curved UI, Kanban tracking, Resume studio, Gmail outreach and Automation center remain. Gmail tokens, reviewed drafts, sending limits, reply/bounce handling and send checkpoints stay protected. The previous PostgreSQL verification completed 1,000 unique claims across eight concurrent threads; that benchmark predates the new fair scheduler. See [production setup and limits](docs/PRODUCTION_UPGRADE.md), [owner setup](docs/OWNER_CONSOLE.md) and the earlier [repository audit](docs/research/combined-repositories.md). No live recruiter email, external application, Git publishing or cloud deployment was performed.

The initial candidate preferences are India, graduation in 2029, beginner-friendly undergraduate technical internships, remote work, research and student programs. Name, contact information, education details, experience and projects start empty. You must provide and verify them before they can appear in application materials.

Both explorers now separate nearby opportunities (Nagpur/Pune by default), the rest of India, international locations and worldwide locations. Local cities and named nearby groups are editable. Broader regional announcement searches can be enabled when `BRAVE_SEARCH_API_KEY` is configured; existing public feeds work independently. See [regional discovery and coverage limits](docs/REGIONAL_DISCOVERY.md).

External submissions are not enabled by the shipped adapters. Public ATS discovery works independently of submission permission. The supported submission adapter is an isolated local test portal; external forms use assisted preparation and manual completion. See [connector coverage](docs/connectors.md), [executed verification](docs/TEST_REPORT.md) and [limitations](#current-limits) before treating a new platform as supported.

## Run online

The [production guide](docs/PRODUCTION_UPGRADE.md) and [cloud Compose configuration](deploy/compose.cloud.yaml) separate API, frontend, crawler, browser and outreach workers with managed PostgreSQL, private Redis, persistent volumes and Caddy HTTPS. This runs with your laptop off when deployed to an always-on server. A modest deployment is budgeted at roughly US$35–90/month, subject to current provider pricing and workload. Gmail/search credentials, DNS and server access must be configured. The [hosting guide](docs/hosting.md) and [Render Blueprint](render.yaml) remain a smaller alternative. The source package is not a live deployment.

## Start on Windows 11

Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) with WSL 2 and Linux containers. Start Docker Desktop, open PowerShell in this directory, and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

The script creates `.env`, generates a Fernet encryption key and database/Redis passwords without printing them, validates Compose, builds the images, waits for healthy services, and opens **http://localhost:3000**. First installation downloads Chromium and dependencies and can take several minutes. The frontend and API ports bind to the local machine; PostgreSQL and Redis have no host ports.

Create an account in the UI. Registering never submits an application. Complete the profile and confirm each field you want used. Review the default public discovery sources, run discovery, and inspect evidence and uncertain eligibility on each listing. Sources can be added, disabled, or rescheduled in the interface.

```powershell
.\scripts\stop.ps1              # Stops services; preserves all volumes
.\scripts\start.ps1             # Rebuilds if needed and resumes services
.\scripts\test.ps1              # Runs backend automated tests in the image
.\scripts\backup.ps1            # Consistent database + encrypted-file backup
docker compose ps
docker compose logs --tail=100 backend worker
```

If local PowerShell execution policy blocks `.ps1` files, invoke the needed script with `powershell -ExecutionPolicy Bypass -File <script>`. Scripts do not change the machine-wide policy. Keep an encrypted backup of `ENCRYPTION_KEY` separate from the database backup; losing it makes candidate records and documents unreadable.

## Linux and macOS

With Docker Compose v2 and Python 3 installed:

```bash
./scripts/setup.sh
```

Use `python3 scripts/setup_env.py` followed by `docker compose up --build --detach --wait` if you prefer individual steps. Setup is idempotent: existing nonempty keys are preserved. No `.env` contents need to be pasted into a terminal.

## Use the application

1. **Profile:** supply accurate details and verify fields. Resume imports yield proposals for your review; imported text is not a verified qualification.
2. **Discovery:** run configured public sources and review source health. Source failures stay visible. A missing publication date stays unknown; the system records first discovery and last verification separately.
3. **Eligibility:** review explicit graduation years, geography, skills, experience and other extracted requirements. Incompatible years are rejected. Missing or ambiguous critical requirements require review. A high score does not certify eligibility.
4. **Documents:** generate a tailored PDF resume or cover letter from verified existing facts. Each version is retained. No employer requirements are converted into candidate achievements.
5. **Applications:** switch to Assisted Apply to prepare a factual PDF and checklist. Review the draft, then approve this specific document/profile/listing before external browser preparation. Changing candidate facts invalidates approval. External final submission is manual; no working general auto-submit adapter is claimed.
6. **Policy and alerts:** opt into automatic drafting with a score threshold and daily limit if desired. The worker prepares eligible documents and stops for review. Automatic mode also enforces employer/origin allowlists; it grants no upload/message consent. Configure quiet hours and review individual outbound messages under Notifications. Ambiguous, sensitive, legal, CAPTCHA and MFA questions pause.
7. **Emergency stop:** prevent further scans/preparation and stop the worker before an approved upload or supported local submit action. It cannot undo a request already received by a service.

Only a detected confirmation is recorded as a successful submission. An uncertain outcome is held for reconciliation and is not automatically submitted again. Application/interview/assessment status can be manually updated; there is no automatic email inbox access in the default deployment.

## Run the authorized local demonstration

The test portal exists only with `TEST_MODE=true`. It is not an external employer and accepts clearly identified synthetic test data. The demo never applies to a real internship.

For an isolated Docker demonstration, create a separate checkout/directory or back up your data, then:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1 -TestMode
```

Create a dedicated test account. Use the dashboard's local demo controls to seed labeled fixture opportunities and run the local end-to-end workflow. The workflow exercises real Playwright field filling, PDF upload, a screenshot before submission, POST to the test portal and confirmation detection. A fixture with a sensitive question pauses for human input. Duplicate protection and restart recovery are covered by automated tests. Do not put fictitious demo details into your real candidate profile.

Turn `TEST_MODE=false` in `.env` and run `docker compose up -d --force-recreate backend worker` when finished. Test fixtures remain explicitly labeled in that account. No local demo result is represented as a real employer submission.

If Python is installed on the host, the command-line client provides the same authorized demonstration and checks duplicate prevention. It prompts for the password and accepts only a loopback API URL:

```powershell
python scripts\demo.py --email local-demo@example.test --register --artifacts artifacts\local-demo
```

Omit `--register` to use an existing test account. The API and worker must both be running with test mode enabled. The command saves the generated PDF, pre-submit screenshot and confirmed result when `--artifacts` is supplied.

A captured public-listing snapshot also supports a read-only, offline ranking demonstration without credentials or a running database:

```bash
python scripts/replay-discovery.py --output artifacts/offline-replay.json
```

The output is explicitly labeled historical data, re-extracts requirements and ranks those actual listing descriptions for India/2029. It does not claim those positions are still open or create any application.

## Native development

Use Python 3.12, Node.js 22 LTS and npm. Windows helper:

```powershell
.\scripts\dev.ps1 -Task setup
# Open three separate PowerShell windows:
.\scripts\dev.ps1 -Task api
.\scripts\dev.ps1 -Task worker
.\scripts\dev.ps1 -Task web
```

Equivalent shell steps:

```bash
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
backend/.venv/bin/python -m playwright install --with-deps chromium
python3 scripts/setup_env.py
cd frontend
npm ci
npm run dev
```

In two additional terminals, run `cd backend` and then `.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload` or `.venv/bin/python -m app.worker`. On Windows the executable is `.venv\Scripts\python.exe`. Native mode uses SQLite unless `DATABASE_URL` points to PostgreSQL; Docker overrides the URL with its PostgreSQL service. Run the API and worker from the same backend directory so their default data path agrees. Next.js proxies `/api/*` to `INTERNAL_API_URL`.

Migrations apply on API startup and are serialized on PostgreSQL. To run explicitly:

```bash
cd backend
.venv/bin/python -m app.migrate
.venv/bin/python -m pytest -q
cd ../frontend
npm run typecheck
npm run lint
npm run build
```

## Configuration

Copying `.env.example` manually requires setting `ENCRYPTION_KEY`, `POSTGRES_PASSWORD`, and `REDIS_PASSWORD` before using Compose. The setup scripts do this correctly. Keep `.env` out of Git and backups that are not encrypted.

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | Native SQLAlchemy URL; Compose supplies PostgreSQL automatically. |
| `DATA_DIR` | Private runtime data directory; `/data` in containers. |
| `ENCRYPTION_KEY` | URL-safe Base64 encoding of 32 random bytes. Fixed for existing encrypted data. |
| `COOKIE_SECURE` | Set `true` when serving the app through HTTPS. Local HTTP uses `false`. |
| `ALLOW_REGISTRATION` | Disable new account creation after onboarding if desired. |
| `CORS_ORIGINS` | Comma-separated explicit frontend origins; use the same-origin Next proxy normally. |
| `WORKER_CONCURRENCY` | Bounded worker concurrency, default 2. |
| `TASK_LEASE_SECONDS` | Task crash-recovery lease, default 180 seconds. |
| `REDIS_URL` | Optional event transport. PostgreSQL is the source of truth for tasks. |
| `TEST_MODE` | Default `false`; mounts the local test portal and enables demo fixtures only when true. |
| `TEST_PORTAL_ORIGIN` | Exact trusted local test origin, `http://backend:8000` inside Compose. |
| `LLM_PROVIDER` | `disabled` by default; `openai_compatible` enables optional structured job interpretation. |
| `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` | Server-side LLM endpoint and credentials. Only public job description text is sent. |
| `BRAVE_SEARCH_API_KEY` | Optional authorized search discovery; requires a configured search source. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_STARTTLS` | Optional TLS email delivery; every message requires specific approval. |
| `TELEGRAM_BOT_TOKEN` | Optional Telegram provider; destination is saved privately in Notifications. |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM` | Optional authorized WhatsApp delivery; provider rules and per-message approval apply. |

Optional LLM output is advisory, carries exact source quotations, and cannot override deterministic rejection, verify candidate data, answer application questions or activate submission. Deterministic matching and PDF generation work without an LLM.

## Project layout

```text
frontend/            Next.js dashboard and same-origin API proxy
backend/app/         FastAPI, models, encrypted storage, migration, worker
backend/tests/       Discovery, ranking, documents, API and browser tests
scripts/             Windows/Linux setup, development, test and backup helpers
docs/                Connector support and operating procedures
compose.yaml         PostgreSQL, Redis, API, worker and frontend
.env.example         All supported operator configuration, no credentials
```

The durable database queue claims tasks with leases and uses idempotency at the candidate/opportunity boundary. Browser storage state and private documents are encrypted. Passwords are scrypt hashes; session tokens are opaque and server-side records store token digests. Mutation requests require a CSRF token. Records and downloads enforce ownership. See [operations and recovery](docs/operations.md) and [security boundaries](docs/security.md).

## Current limits

- This is a single-node, local-first installation. It has no public hosting configuration, distributed browser fleet or independent security audit. A public deployment requires TLS, registration restrictions, provider terms review, backup operations and load/security testing.
- Shipped external ATS connectors discover listings; they do not certify permission to submit forms automatically. External submission adapters must be implemented and verified individually before they can qualify for Auto Apply. No worker bypasses CAPTCHA, MFA, authentication or anti-bot restrictions.
- No licensed LinkedIn, Indeed, Wellfound, Internshala or Unstop integration is bundled. Direct crawling of those platforms is disabled. Use permitted feeds or official sites and manual application where needed.
- Workday public CXS discovery returns listing metadata with uncertain eligibility. SmartRecruiters/Workday board caps are surfaced in source cache metadata; large boards may require pagination enhancements. There is no claim of complete internet coverage or guaranteed discovery latency.
- Eligibility extraction is conservative and cannot interpret every legal, academic or employer-specific requirement. Uncertain cases remain in review. Compensation and original posting dates often are unavailable.
- Status updates, in-app/browser alerts and approved email/Telegram/WhatsApp delivery are implemented. Provider credentials are optional and no live delivery is claimed without them. Automatic email confirmation ingestion is not implemented. A completed browser click without confirmation remains uncertain.
- Resume parsing supports readable PDF, DOCX and UTF-8 TXT, with size limits. Scanned PDFs require OCR outside this application. PDF tailoring orders and selects verified facts; it does not invent a stronger history.
- PowerShell scripts are included for Windows 11, but this Linux build environment cannot execute a full Windows/Docker Desktop acceptance run. See the [test report](docs/TEST_REPORT.md) for checks actually executed in this workspace.

Do not run tests against a real employer endpoint without a separate explicit authorization. Tests and the demonstration use local fixtures; ordinary discovery is read-only.

## Source archive

Run `python scripts/package.py` to create `dist/InternPilot-AI.zip` from allowlisted source, setup files, docs and curated public/synthetic test evidence. It excludes runtime databases, credentials, `.env`, browser state, dependency directories and build output. The script verifies archive CRCs and every SHA-256 manifest entry before replacing the archive.
