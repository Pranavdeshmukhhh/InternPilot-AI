# Founder access, startup and security release

29 October 2026. This release preserves the current Next.js/FastAPI/PostgreSQL/Redis architecture and existing candidate data. The internal role is still named `owner`. There is no shared or hardcoded master password and no public owner registration endpoint.

## Your login and fast local startup

Install Docker Desktop on Windows 11 with WSL 2 and Linux containers. Extract the updated ZIP into a new folder, retaining your existing private `.env` and database volumes if upgrading. Run `scripts/run_local.bat`, or PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\quickstart.ps1
```

The launcher generates missing secrets without printing them, installs locked dependencies through Docker image builds, starts the database/Redis/API/frontend/worker, waits for service health, and opens `/login`. If no founder exists, it asks you for your founder **email**, **password**, and password confirmation with hidden password entry. Those are your login credentials; they are created on your machine and are not bundled in the ZIP or committed. Existing founder passwords are not reset or recoverable from their salted hashes. Initial image downloads/builds can take longer than a few minutes; subsequent launches reuse caches. Native Windows and full image builds were not executed in the managed Linux QA environment.

Docker is the supported Windows route: the Linux Python lock includes uvloop. The previous extra `run_local.bat` skipped dependency installation and never launched a worker, so a seemingly running frontend could have missing React Query modules, an unavailable API or a stalled application queue. The replacement exits on failure and uses the integrated Compose startup. Do not run the old native frontend/backend windows on ports 3000/8000 alongside Compose.

If provisioning separately:

```sh
docker compose exec backend python -m app.admin create-owner
# For an existing ordinary account, and only when no founder exists:
docker compose exec backend python -m app.admin grant-owner
```

Sign in with that chosen email/password, open Owner, confirm your password and consent, then access the nine sections. Members includes invitations, account locks, session revocation, audited profile/application inspection and password recovery. Security offers optional authenticator enrollment. Add the displayed setup key manually to your authenticator; confirm a fresh six-digit code. No third-party QR service receives the key. Use synchronized server/device clocks.

## Founder exclusivity and migration 8

An additive numbered migration adds MFA credentials, recovery tokens, security events, account recovery/version fields and session MFA timestamps. A database partial unique index permits at most one `owner`, including under concurrent provisioning. Public registration always creates members; role fields are rejected. Existing IDs, encrypted documents/profiles and application references are preserved.

Stop writers and back up with the existing key before deploying migrations. If several legacy owners exist, migration 8 deliberately stops rather than guessing which is yours. With API/workers stopped, run the new image's trusted CLI:

```sh
docker compose run --rm --no-deps backend python -m app.admin select-founder
```

It asks for an existing account's email, selects that sole founder, demotes other owners to members and revokes affected sessions. It does not delete their data. On cloud Compose the service is `api`, and commands include `--env-file .env.cloud -f deploy/compose.cloud.yaml`. Keep activation closed during upgrade and offline transfers. Complete migration before starting the matching API and workers. Host administrators and database superusers remain trusted infrastructure authorities; this web application cannot defend against their direct database modification.

Rollback is additive/forward-repair preferred. Do not drop new security tables or the unique index, and never reopen old authentication code while forced-reset accounts exist: old code does not understand the reset-required flag. Keep login/activation and workers closed, restore the matching image/database/key backup in isolation, reconcile security changes and outbound receipts, then reopen deliberately. No destructive down migration or production restore was performed.

## Recovery and sensitive actions

- Privileged actions require server RBAC, session-bound CSRF, fresh password, explicit consent/purpose, and recent MFA when enabled. Reports require a server-side, session-bound five-minute reauthentication grant. Changing password/MFA invalidates that grant. UI visibility and URL secrecy are not authorization controls.
- Passwords use per-password random salts and scrypt. Credentials, stored hashes, browser cookies and private custom-answer vaults are never returned to founder reports. MFA keys are encrypted and revealed only to the authenticated account during its deliberate setup. Status endpoints do not retrieve them afterward.
- In Members, issue a recovery link after reauthentication. It expires after 30 minutes, is shown once, and is shared privately by you; no email is sent automatically. Only its digest is stored. Issuance immediately requires password recovery, revokes sessions, and pauses that member's automation. Redemption is atomic and one-use, including concurrent requests. Subsequent issuance/password changes invalidate earlier links. A disabled account stays disabled. MFA remains enabled after password recovery.
- Founder recovery is deliberately not available through member recovery endpoints. At a trusted local terminal use `python -m app.admin reset-password` inside the backend container. If the authenticator is lost, `python -m app.admin reset-password --disable-mfa` explicitly resets the password, clears MFA, revokes sessions and pauses automation. Passwords use hidden prompts; never pass them as command arguments. Enroll MFA again after recovery.
- The old fresh-password-protected replacement-password API remains for compatibility; the standard dashboard now issues recipient-chosen recovery links instead.

## Real reports, privacy and infrastructure

Overview/Analytics query actual member counts, active sessions, locks, reset flags, registration dates and application statuses. Activity/Security show bounded security and audit projections. Failed passwords, disabled-account sign-ins and failed MFA are recorded without password/request bodies. Address correlation tags are keyed one-way values, not raw IP addresses, and failed attempts are signals for review rather than proof of abuse. Older sign-in history remains in the existing audit table; there is no invented historical backfill.

Members shows actual supplied names (or “not provided”), emails, dates, activity and session counts. Default pagination and exact email lookup run in SQL, with one grouped query for session counts. Legacy partial search is bounded to 1,000 accounts and explicitly reports truncation. Private profile inspection still requires its own password/purpose and is audited. Worker/source/queue reports observe actual stored health; a recent heartbeat is not an uptime guarantee. No SQL shell, infrastructure passwords, deployment keys or unrestricted system commands are exposed.

Run `python -m app.security_maintenance` daily using a private operator scheduler and the backend environment. It deletes at most 1,000 expired records per table per invocation: security events older than 30 days, recovery metadata expired more than 30 days, expired sessions and expired report grants. Repeat bounded runs for backlog. Invitation and unrelated coordination namespaces are untouched. This task prepares the command; no cloud scheduler was installed. Configure trusted proxy address handling and NAT-appropriate limits before a shared deployment.

## Secrets, Git history and deployment

Git/Docker exclusions and source packaging reject real dotenv files, runtime databases, backups, exports and private key containers. `.env.example` remains placeholders. Production secrets belong in private deployment settings or a secret manager, never `NEXT_PUBLIC_*`, source, documentation or the downloadable archive. Frontend configuration rejects credential-bearing API URLs and credential-like public variables without echoing the value. SQLAlchemy hides bound parameters in exception logs. Production PostgreSQL now requires `verify-full`; configure a trusted database CA/PGSSLROOTCERT where needed. This is stricter than the older SSL `require` option and must be configured before upgrading an existing production deployment.

Gitleaks 8.24.3 scanned all fetched reachable main history: five public GitHub commits and sixteen prior local commits. Initial findings were fifteen release checksums and explicit synthetic test encryption material, verified against the corresponding Git blobs. Exact historical fingerprints are documented in `.gitleaksignore`; there are no whole-test-directory exclusions. The wrapper also recognizes a release checksum only when it matches the actual file in that commit. No live credential was confirmed, so no healthy encryption keys were rotated. Pattern scans do not prove absence of every secret, personal datum, deleted fork, artifact or unreachable ref.

CI downloads the checksum-pinned scanner, rejects tracked runtime paths and scans reachable history with redaction. Reports omit secret and match values. The actual installer, local scans and browser JS bundle scan were exercised. Hosted Actions were not executed. Keep old backups encrypted, outside the checkout, with keys stored separately. If a real exposed credential is found later, revoke/rotate it at its provider first; do not blindly replace the encryption key and lose access to existing data.

## Validation and current limits

- Full backend run: **546 passed, 2 PostgreSQL-only skips**, one existing deprecation warning. Later migration/owner regressions: **44 passed, 2 skipped**; strict TLS hosting checks: **22 passed**. Additional transfer, recovery/MFA and maintenance checks are recorded under `artifacts/founder/`. One final migration test initially hit an API fixture startup timeout under concurrent builds; the rerun passed both checks with a 30-second fixture readiness budget.
- Four founder browser groups passed: report unlock/projections/mobile layout, actual recovery-link redemption, MFA enrollment and MFA-required login, grant invalidation/re-unlock and accessibility. Zero axe violations in that checked founder screen. Existing five invitation/access groups passed. Screenshots contain explicitly synthetic local accounts only.
- Frontend production build, typing, lint, unit tests, OpenAPI contract drift and formatting passed before the final pipeline follow-up; final pipeline unit tests and frontend checks passed; evidence accompanies the updated archive. Pipeline fix keeps `submitting` and unknown future statuses visible and includes approved work in progress and failed work in attention. No prepared application is called submitted.
- The public Site still hosts only the landing/demo/access introduction. This private account backend and founder console are not publicly deployed. No real mail, external applications or production changes were performed. Existing egress/DNS-rebinding, independent runner isolation, quota/capacity and full-size offsite recovery gates in SECURITY_REVIEW/PERFORMANCE_REPORT remain. This change does not certify the entire platform as production-ready.
- GitHub connection lists no writable repository for this owner. Changes are delivered as reviewed source/ZIP, without claiming a remote push. No founder email/password was guessed or hardcoded.
