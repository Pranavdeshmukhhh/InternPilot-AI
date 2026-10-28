# Operating InternPilot

For schema version 5, separate cloud worker pools, Gmail setup, measured queue behavior, scan retention, encrypted backups and deployment costs, use the current [production operations guide](PRODUCTION_UPGRADE.md). The earlier local/single-service instructions below remain supported. No cloud provisioning is implied by a configuration file.

## Service topology and persistence

`frontend` proxies API requests to `backend`. PostgreSQL stores accounts, encrypted candidate profiles, opportunities, applications, task leases, notices and audit records. `worker` claims database-backed tasks and runs discovery/preparation. Redis is an optional transport; it is not the authoritative application queue. The `app_data` volume stores protected runtime artifacts. The API and worker share that volume and encryption key.

Docker services restart with `unless-stopped`. `docker compose stop` preserves state. `docker compose down -v` deletes volumes and must not be used as an ordinary stop or troubleshooting step. Do not replace or regenerate the encryption key for an existing installation.

## Routine checks

```bash
docker compose ps
docker compose logs --tail=100 backend worker
docker compose exec -T backend python -m app.migrate
```

The API's `/api/health` endpoint is used for process readiness. Check source health and recent events in the dashboard for connector failures. Rate limits, permission errors, parsing failures and unsupported forms appear as failures/review requests. A healthy API does not prove an external board is accessible.

Dashboard metrics derive from persisted records. Discovery latency is measurable only when a real publication timestamp exists; missing timing samples remain unavailable. Submission success means a supported adapter observed a confirmation, not that an employer accepted the candidate or scheduled an interview.

## Restart and uncertain submissions

Tasks have renewable leases. A worker restart can reclaim pre-submit tasks after the lease expires. A persisted submission-in-progress state is treated as uncertain after interruption; it is held for human reconciliation. Do not force-retry an uncertain or confirmed application.

To reconcile, inspect the screenshot, official portal and any employer confirmation you obtained independently. Record the actual status. If no confirmation exists, the dashboard must continue to show an uncertain outcome; absence of an email alone does not prove rejection or failure. Application idempotency persists in the database and survives container restarts.

The emergency stop is a candidate policy flag checked again before final submission. It cannot undo a request already received by an external service. Stop the worker container as an operational fallback if the UI/API is unavailable; leave the database intact for recovery.

## Backups

On Windows run `scripts/backup.ps1`. The helper stops API and worker briefly, creates a PostgreSQL custom-format dump and a separate archive of private runtime files, then starts the services again. PostgreSQL and Redis remain running. Store backups on an encrypted disk or encrypted backup service. The script does not copy `.env`; back up `ENCRYPTION_KEY` separately in a password manager or encrypted secrets archive.

For native SQLite, stop API and worker, copy the whole configured data directory including any encryption key and SQLite WAL/SHM companions, then restart. Prefer SQLite's backup API if you cannot stop writers. Retain the exact encryption key that protected the records.

Restore into a separate test installation first. Restore the database using `pg_restore` with the original schema owner, restore `/data`, set the original encryption key, and start API/worker. Review unresolved tasks before enabling application modes. The repository does not provide a destructive one-click restore command.

## Updating

1. Stop new applications with emergency stop and let known pre-submit tasks settle.
2. Back up the database, private runtime files and original encryption key.
3. Update source and dependency locks; read migration changes.
4. Run `docker compose up --build --detach --wait`.
5. Check source health, user login, profile decryption and a local test workflow before resuming applications.

Schema version 1 is applied by `python -m app.migrate`; later schema changes should add numbered migrations. Database initialization is guarded by a PostgreSQL advisory lock. Do not use schema recreation as an upgrade method.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Docker engine unavailable on Windows | Start Docker Desktop; select Linux containers and WSL 2. |
| Browser installation fails | Check disk space, corporate proxy/CA settings and access to Playwright download hosts. Keep TLS verification enabled. |
| API cannot decrypt profile | Restore the original `ENCRYPTION_KEY`; never generate a replacement to clear the error. |
| Discovery 401/403 or robots refusal | Disable the source or configure a permitted API/feed; do not bypass access controls. |
| Discovery 429 | Respect retry/backoff and increase the source interval. |
| Application waits for input | Review unknown/sensitive fields or unsupported adapter; do not fill invented answers. |
| API works but frontend login fails | Use the same frontend origin, check `INTERNAL_API_URL`, cookie security and CSRF errors. |
| Demo is unavailable | `TEST_MODE` defaults to false. Explicitly enable only in an isolated test account/deployment. |
| Host ports are occupied | Change `APP_PORT` or `API_PORT` in `.env` and recreate services. |

The default Compose configuration is for a local user on a trusted device. The [hosted deployment](hosting.md) supplies a cloud container and managed PostgreSQL Blueprint, secure cookies, exact HTTPS origins, invitation-only registration, and worker readiness monitoring. For another provider, configure equivalent HTTPS, persistent encrypted storage, restricted database access, backups, and restart management. Do not expose PostgreSQL, Redis or a test portal to the internet.

## Proxy trust in managed build environments

Normal Windows Docker Desktop builds use system/public CAs. In a managed environment with an HTTPS inspection proxy, the Dockerfiles support an optional BuildKit secret named `proxy_ca`. Supply the combined trusted CA bundle to each networked build, for example:

```bash
docker build --secret id=proxy_ca,src=/path/to/trusted-ca-bundle.pem -t internpilot-backend ./backend
docker build --secret id=proxy_ca,src=/path/to/trusted-ca-bundle.pem -t internpilot-frontend ./frontend
```

Do not copy session CA files or credentials into images, disable TLS verification or use host networking to bypass egress policy. Runtime proxies may also need a read-only CA mount and the provider client's supported trust environment variable.

For a runtime HTTPS inspection proxy, use a deployment-local Compose override that mounts the operator's combined trusted CA bundle read-only and sets `SSL_CERT_FILE` for both `backend` and `worker`. Include the normal public roots as well as the authorized inspection root. This was necessary in the managed validation environment: public ATS reads failed safely until the runtime trust bundle was supplied, then Greenhouse returned HTTP 200 with certificate verification enabled. The session-specific CA and validation override are not part of the shipped default configuration.


## Upgrade automation and notification controls

Schema version 3 adds bookmarks, encrypted notification preferences/outbox records and upload checkpoints. Migrations are additive and serialized on PostgreSQL. Back up the database and original encryption key before updating; the migration runner is safe to call repeatedly.

Worker heartbeats and queue counts are visible in Overview and Activity. `/api/health` checks the API process; `/api/ready` also checks the database and, where configured, the supervisor heartbeat. Source failures back off; manual scans cannot override an active failure delay. In-app match/change alerts and deadline reminders deduplicate persistently. Automatic PDF preparation is opt-in, score-limited and budgeted per UTC day; it never implies upload consent.

Configure optional provider secrets in the server environment using `.env.example`. Save private destinations and quiet hours under Notifications. Each message is a previewable draft until specifically approved. A provider's acceptance is recorded as `sent`, not as recipient receipt. Quiet-hour deferrals require a later approval. Rejected, uncertain or interrupted delivery attempts are never automatically resent. An abandoned send checkpoint becomes uncertain after ten minutes.

A document upload approval binds the exact generated document, verified profile and listing snapshot. If facts change, generate and review a fresh draft. After an upload checkpoint, worker failure or lease expiry becomes uncertain; inspect the official portal before any further action. External final submission remains manual. Do not clear checkpoints to force a retry.

Use Account security to change your password or sign out other sessions. For local account recovery, run `python -m app.admin reset-password your-email` in the configured backend environment. It prompts without echo, revokes existing sessions and activates emergency stop. Never put a password on the command line.

Schema version 4 adds explicit member/owner roles, disabled-account state and last-login/last-seen timestamps. Existing users default to members. Owner provisioning is local-only; see [owner setup](OWNER_CONSOLE.md).
