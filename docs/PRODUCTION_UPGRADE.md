# Production upgrade: current implementation

The existing Next.js / FastAPI / SQLAlchemy application was upgraded in place. Internship and hackathon discovery, India/international/local views, encrypted profiles and documents, named-owner RBAC, factual PDF generation and guarded application workflows are retained. No cloud account, Gmail credential or search credential was available in this session. No live deployment, recruiter email or external application is claimed.

## Audit and changes

| Area | Before | Implemented change |
| --- | --- | --- |
| Interface | Existing notebook styling and application list | Floating rounded navigation, restrained violet accent, consistent light/dark surfaces, denser typography, application Kanban/list switch, Resume studio, Recruiter outreach, Automation center and Settings |
| India discovery | India feed, regional filters and ATS readers | Live-checked Sarvam AI Ashby board, source catalog, research/government search configurations, strict skill/degree/year/month-duration/monthly-INR filters |
| Queue | Durable DB leases, priority claims, local source-host limits | One durable job per source, bounded scheduler batches, bulk import of up to 1,000 source configurations, 2,000-source per-user quota, dedicated worker roles, PostgreSQL host budgets across replicas, bounded browser pool and adaptive capacity |
| Observability | Worker presence and audit events | Persisted scan outcomes, record counts, timings, sampled p95, queue and worker statistics; no simulated live counters |
| Outreach | No recruiter email workflow | Gmail OAuth with PKCE, session-bound expiring single-use state, encrypted offline tokens, pinned Google endpoints, verified sender identity, factual draft generation, edit/review/schedule, quotas and gaps, known-thread reply tracking, opt-out/bounce handling and stop-on-reply |
| Reliability | Conservative browser checkpoints | Equivalent durable email send checkpoint, uncertain receipt state, Gmail sent-mail reconciliation and no automatic retry after send began |
| Storage | Version 4 migrations | Additive version 5 tables and indexes; existing encrypted records and the storage key are preserved |
| Operations | Local Compose and smaller hosting blueprint | Separate cloud crawler/application/outreach workers, managed PostgreSQL, Redis, automatic HTTPS through Caddy, persistent volumes and authenticated stream-encrypted backups |

## Gmail setup and truthful states

Create a Google Cloud OAuth **Web application**, enable the Gmail API, and register the exact redirect URI. Set `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET` and `GMAIL_REDIRECT_URI` server-side. Local callbacks use `http://localhost:3000/api/outreach/gmail/callback` or the equivalent 127.0.0.1 origin you actually open. Hosted callbacks must use the exact trusted HTTPS application origin.

Requested scopes: `openid`, `email`, `gmail.send`, `gmail.readonly`. Google can require restricted-scope verification and possibly an independent security assessment before broad public production use. Testing-mode grants may expire after seven days. Configure Google test users and the consent screen correctly; a functioning implementation is not proof that Google has approved a production app.

Session cookies use SameSite=Lax to allow Google's top-level OAuth return. Existing session-bound CSRF and strict mutation-origin checks remain enforced. OAuth state is additionally bound to the current account and session, expires after ten minutes and is consumed before exchange. Access logs redact callback code/state query parameters. Refresh tokens and access tokens remain encrypted in the database; public APIs never expose them. Disconnect removes local tokens and invalidates approvals; revoke the provider grant under Google Account third-party access when required.

Add only personally verified recruiter contacts and a public provenance link. The app does not discover, guess or purchase email addresses. Verify the candidate name and at least one factual project before drafting. Templates support only documented factual placeholders; generated outreach uses verified facts and does not send profile text to an LLM. All email content is plain text. Editing invalidates approval. Profile or sender changes invalidate queued approval. Every specific message needs consent; enabling a sender policy alone cannot send it.

Defaults: 35 messages/day, maximum 40, a 15-minute minimum gap, weekdays 09:00–19:00 Asia/Kolkata. Lower provider quotas still apply. Sender windows, limits, gap, tone, signature and templates are editable. The maximum is a ceiling, not a target. Gmail authenticates the sending account; custom domains must have provider-managed SPF/DKIM/DMARC correctly configured. The app does not claim to verify those DNS records or guarantee inbox delivery.

States: `draft` → `approved` → `sending` → `sent` only with a Gmail message ID and thread ID. **Sent means provider acceptance, not recipient delivery.** A timeout, missing receipt or restart after the send checkpoint becomes `uncertain`; it is never automatically resent. Reconcile searches sent mail by the fixed RFC Message-ID. Gaps and daily quotas count reserved/uncertain attempts conservatively.

The worker checks at most 25 known sent threads per sync and rotates the cursor; up to 100 messages per thread are considered. Reply text is bounded and encrypted. Verified-contact replies stop further queued outreach. Recognized opt-outs and delivery-status notices in these known threads also stop outreach. A separate bounded Gmail query checks delivery-status notices from mailer-daemon/postmaster over the past 30 days, paginates 25 at a time and matches both the original RFC Message-ID and recipient before recording a bounce. Read permission does not imply automatic ingestion of the whole mailbox. HTML-only replies still stop outreach as replies, but their opt-out wording may not be classified. Provider/Gmail delays and the polling interval mean stop-on-reply is not instantaneous.

Follow-ups are drafts created manually after the configured 3–30-day interval, at most two. Each needs fresh approval. A fresh known-thread sync runs before sending a follow-up. Replies, bounces or opt-outs block them. The app does not implement unattended follow-up campaigns or spam-filter evasion.

## Continuous cloud operation

The new `deploy/compose.cloud.yaml` is intended for an always-on Linux server. It separates API, frontend, crawlers, application workers and Gmail workers. PostgreSQL must be an external managed instance with valid public certificate/hostname verification; Redis stays private. Copy `deploy/cloud.env.example` to a protected `.env.cloud`, preserve the existing Fernet key, supply credentials and point DNS at the server.

```bash
docker compose --env-file .env.cloud -f deploy/compose.cloud.yaml config --quiet
docker compose --env-file .env.cloud -f deploy/compose.cloud.yaml up --build -d
docker compose --env-file .env.cloud -f deploy/compose.cloud.yaml exec api python -m app.admin create-owner
docker compose --env-file .env.cloud -f deploy/compose.cloud.yaml up -d --scale crawler=3
```

Only Caddy exposes ports 80/443; it obtains HTTPS certificates for the configured domain. Configure a host firewall, automated OS/security updates, provider alerts and off-server encrypted backups. Existing local Windows/Compose workflows remain supported. No NVIDIA GPU is required. The smaller Render blueprint is retained as an alternative single-service deployment; the distributed Compose topology is a separate option.

HTTP is the default discovery transport; only specifically approved application work can launch Chromium. `WORKER_CONCURRENCY` is bounded at 32; `BROWSER_CONCURRENCY` at 2 per process (default 1). Separate discovery workers never claim application tasks. PostgreSQL SKIP LOCKED/atomic claims and per-source idempotency support replicas. Shared PostgreSQL host budgets preserve source delays and Retry-After across replicas. SQLite is a single-machine fallback; its benchmark is not evidence of distributed throughput.

The scheduler uses bounded batches. Source refresh periods, backoff and HTTP validators remain in force. Adaptive capacity halves slots when at least five recent completed scans show over 25% failures and restores one slot per check. This is a conservative control based on observed errors, not an autonomous permission to increase a website's rate limit. More replicas cannot override host budgets. High-source-count throughput depends on host distribution, site limits, payload sizes, search quotas and database capacity.

Scan telemetry is retained for 14 days by default and pruned hourly by discovery workers (`CRAWL_LOG_RETENTION_DAYS`, bounded 1–90). This limits operational-table growth at high source counts. Application history, audit logs, candidate records and opt-out contacts are not deleted by this housekeeping task.

Budget estimate, not a provider quote: roughly **US$35–90/month** for a modest always-on server, managed PostgreSQL, small Redis/storage and backups. Multiple browsers or heavy source payloads can need more memory. Search API, LLM, domain registration and Google verification costs are additional. Review current provider pricing before provisioning. Free sleeping web plans cannot meet a 24/7 laptop-off requirement.

## Backups and recovery

`scripts/secure-backup.py` streams `pg_dump` custom-format output through authenticated AES-256-GCM encryption with a key derived from the existing storage key and a fresh random salt/nonce. Passwords are passed to pg_dump through its environment, not argv or logs. Install a `pg_dump` version compatible with the server, normally PostgreSQL 16 tools. Run the script with the backend environment loaded and restrict backup-file and key access.

```bash
backend/.venv/bin/python scripts/secure-backup.py /private/backups/internpilot.dump.enc
backend/.venv/bin/python scripts/secure-backup.py /private/restore/internpilot.dump --decrypt /private/backups/internpilot.dump.enc
```

Output creation is exclusive; existing files are never overwritten. Decryption authenticates the backup and writes a new dump, without modifying a database. A failed authentication removes the newly created partial output. Restore with pg_restore only after choosing an isolated target, reviewing the command and preserving the original storage key. Schedule backups on the cloud host/provider, copy them off-server and test restores. Database payloads include the encrypted documents; keep the encryption key separately. This session tests encrypted streaming roundtrips and tamper rejection; a live cloud restore is not claimed.

## Application support boundary

Discovery/Manual, Assisted and restrictive automatic-draft policies are retained. Automatic drafts require verified eligibility, allowlists/thresholds and limits. Specific external document uploads require separate consent. CAPTCHA, MFA, unsupported or legally significant questions pause. The local synthetic portal remains the only certified final-submit adapter. No general Greenhouse/Lever/Workday auto-submission integration is claimed: it would require the employer's permitted endpoint/credentials, form contract and separate acceptance testing. Prepared applications are never recorded as submitted.

## Evidence and remaining prerequisites

- **434 backend tests passed**, no failures/errors/skips, in 156.85 seconds. [JUnit](../artifacts/production-backend-tests.xml).
- **41 browser checks passed** (24 existing, seven regional, ten new), including local upload/receipt, owner/account controls, source pagination, Kanban/list/detail, contact/draft/edit/opt-out workflows, provider blockers, dark mode, account switching and 390/768/1024px layouts. [New suite](../artifacts/production-ui.json).
- PostgreSQL: migration 4→5, preserved encrypted profile, repeated migration, 1,000 unique source-job claims across eight concurrent threads and one shared host reservation. Scheduling: 2.3818s; claim/complete: 4.6970s. This is a local queue benchmark, not network crawling or production TLS. [Report](../artifacts/production-postgres.json).
- Frontend lint/typecheck/build, backend/script Ruff and `pip check` passed. Production `npm audit` returned zero known vulnerabilities; this is not an independent penetration test.
- Live read-only snapshots: Figma 10, Palantir 46, Ramp 6, MLH 70, InternScan India 11, Sarvam AI 3 records. Sarvam's records were marketing internships; employer identity does not imply AI-engineering availability. [Snapshot](../artifacts/production-live-sources.json).
- Local/cloud Compose validated. Full image rebuild, cloud provisioning, live Gmail authorization/delivery, high-scale HTTP load testing and cloud restore remain unverified. Workspace disk space was under 1 GB; native production builds/tests and actual PostgreSQL checks were used.

Current test artifacts are packaged with the release. OAuth, token refresh, Gmail sending/replies and failure cases are tested with synthetic Google responses; no live email is sent. The queue benchmark measures 1,000 real isolated database tasks and explicitly makes zero HTTP requests/browser launches. Live public API checks are separate from synthetic browser fixtures. Credential-dependent integrations remain disabled until configured. Cloud deployment, external employer integration certification, Gmail production approval and real deliverability tests require operator credentials/authorization and are not claimed complete by source code alone.
