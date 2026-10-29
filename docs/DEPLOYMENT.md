# Reproducible deployment and operations

The full workspace is a deployment candidate. A separate read-only [public preview](https://internpilot-ai-notebook.antigravityfree101.chatgpt.site) is deployed; its allowlisted static build excludes accounts, APIs, credentials and workers. [Deployment evidence and update/rollback procedure](PHASE9_LAUNCH.md). Resolve the P0 network/runner boundaries in SECURITY_REVIEW before exposing an untrusted multi-tenant service. Keep existing user data and encryption keys intact.

**Current account admission:** [ACCESS_CONTROL.md](ACCESS_CONTROL.md) supersedes the earlier shared-invitation-token instructions below. Production requires `INVITATION_ONLY=true`; owner-issued one-use invites replace the shared registration secret. `ALLOW_REGISTRATION=false` still closes activation entirely. Bootstrap a named owner through the local admin CLI and keep activation closed during upgrades/rollback. The public Site has a truthful `/login` entry page, not the deployed account API.

## Local Windows / Linux

Windows 11: Docker Desktop, WSL 2, Linux containers, PowerShell; allow roughly 8GiB RAM for the Docker engine and sufficient image/build disk space (several GB). No dedicated GPU. Run `scripts/setup.ps1`, which generates secrets without displaying them, checks Compose and waits for healthy containers. `scripts/start.ps1 -NoBrowser` restarts; `scripts/stop.ps1` preserves volumes. Native Windows parser resource limits are unverified; Docker uses Linux.

Linux: Docker Engine with Compose v2 and Python 3; `bash scripts/setup.sh`. If installing natively use the exact README commands in a fresh checkout, Python 3.12 and Node 22. Node 24 also passed local builds; Node 22 is the image/CI target. Optional providers are disabled without credentials. Never put keys in NEXT_PUBLIC variables.

Run `python scripts/verify-startup.py --origin http://localhost:3000`. It checks web, API and DB readiness; it cannot certify every worker role. Inspect Automation for role/task/source health. Do not test discovery against 1,000 public sources at once; use the local fixture suites.

## Linux always-on evaluation architecture

Use a single always-on Linux VM, Caddy HTTPS, private Redis, persistent application volume and a separately backed-up PostgreSQL service. Keep the modular application/worker image. A laptop-off deployment requires paid/persistent compute; request-only serverless functions and sleeping free services do not provide reliable scheduled workers.

Planning allowance (not a provider quote): VM 2–4 vCPU/4–8GiB $20–60/month, managed PostgreSQL with backups $15–50+, storage/backups/domain $5–15, total roughly $40–125/month before search/LLM/email and traffic. These resources have not been capacity-certified. Thousands of active users require further query/fanout work and measured sizing, not merely a larger VM. Free tiers are suitable for short demos with explicit sleep/storage/quota limits only.

1. Copy `deploy/cloud.env.example` to `.env.cloud`, chmod 600. Use a real domain and managed PostgreSQL DSN, a persistent Fernet ENCRYPTION_KEY, random Redis password and >=32-character invitation token. Generate a Fernet key with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` in a private terminal, not CI logs. For existing data retain its original key. Back up keys separately.
2. Configure DNS A/AAAA records to the VM. Open inbound 80/443 only; use restricted administrative SSH. PostgreSQL/Redis/API have no published cloud ports. Configure verified DB TLS/CA and private networking. Provide controlled egress denying metadata/private ranges; application preflight DNS checks alone are insufficient.
3. Validate without printing expanded configuration: `docker compose --env-file .env.cloud -f deploy/compose.cloud.yaml config --quiet`.
4. Build: `docker compose --env-file .env.cloud -f deploy/compose.cloud.yaml build`. Corporate proxies require their trusted CA supplied via BuildKit; never disable TLS verification. Images are not cryptographic reproducibility guarantees: record base/package/image digests during promotion.
5. With all writers stopped and a verified backup, run `docker compose --env-file .env.cloud -f deploy/compose.cloud.yaml run --rm --no-deps api python -m app.migrate`, then `... api python -m app.catalog_migrations backfill`, then `... api python -m app.catalog_migrations indexes`. Schema version remains 7; concurrent indexes run outside the migration transaction. Avoid mixed-version writers. See PHASE4_ROLLOUT.md for compatibility recovery.
6. Start web only: `docker compose --env-file .env.cloud -f deploy/compose.cloud.yaml up -d --wait`. Discovery and action workers require explicit profiles. This keeps crawls/uploads/messages off during initial inspection. `python scripts/verify-startup.py --origin https://YOUR_DOMAIN --web-only` checks the public route. The worker-dependent `/api/ready` can return 503 until discovery is enabled; verify it without `--web-only` after that. Check TLS/cookies/origins and close registration after inviting intended users.
7. After source permission/rate review: `... --profile discovery up -d --wait`. Action workers use `--profile actions`; do not activate until network/runner isolation, provider setup and action policies are reviewed. Every external upload/send still needs its specific user approval. No external final-submit adapter is certified.

On update, stop `crawler applications outreach api` first, back up, build immutable candidate images, run migration/backfill/index steps, start one API/worker canary, inspect errors and resume gradually. Never run `down -v`. Failure rollback: keep writers stopped, prefer forward repair; code rollback must retain schema compatibility and original keys. Physical rollback restores the verified DB/files snapshot with its matching image, then reconciles outbound receipts/suppressions before enabling actions. Do not replay uncertain sends.

## Backups

`scripts/backup.ps1` is a local stopped-writer database+volume export; its archive is not an encrypted container. Protect/encrypt it before moving off machine. Production: use `scripts/secure-backup.py` in an operations environment with Python dependencies and matching pg_dump installed (not assumed in the app image), DATABASE_URL, ENCRYPTION_KEY and DATABASE_SSLMODE set securely. It streams authenticated encryption and has a hard timeout. Retain keys separately; copy encrypted backups offsite with retention and access control. Managed PITR complements, not replaces, restore drills.

Decrypt to a new 0600 dump with `python scripts/secure-backup.py restored.dump --decrypt backup.ipbk`, restore to a new isolated database using pg_restore, verify document/profile decryption, IDs and migration versions. Pause workers and reconcile actions since the backup before promotion. Phase 7's small two-database drill passed; full-size/offsite RPO/RTO is unverified.

## Health, logs and incidents

- `/api/health`: DB connectivity and capability/configuration flags; no credentials. `/api/ready`: DB plus configured heartbeat-file readiness. Web health alone does not establish every worker role is alive.
- Automation: actual tenant task counts, source health, retries/dead letters; Owner Console provides audited pause controls. Emergency stop revokes further permitted account actions, not already accepted requests.
- `docker compose ... ps` and `logs --tail=100 api crawler applications outreach`; worker logs are structured JSON with safe exception context. Cloud API/worker logs rotate. Alert externally on stale heartbeats, pending age, failure growth, DB connection pressure, storage exhaustion and backup age. Alert integration/account setup is an operator action, not a shipped SaaS monitoring claim.
- On uncertain outbound outcomes: pause actions, preserve audit/checkpoint records, reconcile provider receipts; never solve uncertainty by resending. On suspected key mismatch restore the original key before restart. On queue overload preserve pending tasks and reduce admission/source cadence.
