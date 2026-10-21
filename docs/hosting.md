# Hosting InternPilot AI

The repository includes a Render Blueprint in `render.yaml` and a complete cloud container in `deploy/Dockerfile`. They provision one always-on application service in Singapore, managed PostgreSQL 16, and a 1 GB persistent disk for encryption-key continuity metadata. The provider supplies the HTTPS URL and certificate. There is no published deployment until a Render account and source repository are connected and the paid resources are provisioned.

The application service runs Next.js, FastAPI, and the durable worker together. This keeps the first deployment small and shares one encryption configuration across the API and worker. PostgreSQL stores encrypted resumes, screenshots, browser session state, candidate profiles, the durable queue, application history, notifications, and the audit log. An additional object-storage account is not needed. Redis is optional: the hosted default uses the existing database-backed event stream and queue to avoid another paid service.

## Resources and estimated cost

| Resource | Configuration | Estimated monthly baseline |
| --- | --- | --- |
| Application and worker | `1c-2g`, 1 CPU, 2 GB RAM, one instance | US$25.00 |
| Managed PostgreSQL | `0.1c-256mb`, 256 MB RAM | US$6.00 |
| PostgreSQL storage | 1 GB | US$0.30 |
| Persistent key-continuity metadata | 1 GB minimum disk | US$0.25 |
| Total | Always-on service and persistent database | **About US$31.55** |

These are estimates, not a spending cap or a price guarantee. Review the current quote in Render before provisioning. Workspace subscriptions, tax, bandwidth/build overages, a custom domain, and optional paid search/LLM usage are additional. Autoscaling and automatic deploys are disabled in the Blueprint. The provided configuration does not provision any Redis, LLM, search, or email service.

Sources: [current plan identifiers](https://render.com/docs/compute-plans), [Render pricing](https://render.com/pricing), [Render's example budget](https://github.com/render-examples/sim-on-render), and [storage rates](https://render.com/articles/how-much-does-cloud-application-hosting-cost-for-small-businesses). Pricing checked October 21, 2026; the provider quote takes precedence.

## Deploy

1. Put this source in a dedicated **private** GitHub repository. Include `render.yaml`, `deploy/`, `backend/`, and `frontend/`. Exclude `.env`, keys, local databases, candidate documents, and browser sessions. `.gitignore` and `.dockerignore` cover these files.
2. Connect Render to that repository. Create a **Blueprint** from `render.yaml` and review the resource quote. A connected Render integration can perform the available provisioning steps once account access and budget are supplied. Do not paste cloud API keys or database passwords into chat.
3. Render builds the container, creates the database and disk, and injects `DATABASE_URL`. It generates persistent `ENCRYPTION_SECRET` and `REGISTRATION_TOKEN` values. The application's public origin comes from `RENDER_EXTERNAL_URL`; nothing has to be guessed from the service name.
4. Wait for the service's `/api/ready` check to pass. This checks the database and a recent worker heartbeat through the same frontend that serves the application. Visit the provider's actual HTTPS URL.
5. In Render's Environment page, reveal `REGISTRATION_TOKEN` privately. Use it as the **Invitation code** when creating your own account. Choose your own password and verify your profile facts. Account creation starts in Discovery mode.
6. After creating the intended account, set `ALLOW_REGISTRATION=false` and redeploy to close signups. Existing sign-in remains available. Keep the invitation token private even before signups are closed.
7. Store an encrypted backup of `ENCRYPTION_SECRET` separately from database and disk backups. Keep it unchanged on redeploy. Losing this secret makes the encrypted data unreadable. Do not rotate it as a routine deploy step.

For a custom domain, first configure it in Render and finish its DNS/certificate verification. Set `PUBLIC_ORIGIN=https://your-domain.example` and `CORS_ORIGINS=https://your-domain.example` before using that URL. Multiple exact HTTPS origins can be comma-separated if intentionally supported. A provider-supplied domain needs no purchase.

## Hosted behavior

- `ENVIRONMENT=production` rejects SQLite, unencrypted database transport, insecure cookies, test mode, missing encryption material, unrestricted signup, missing worker monitoring, and invalid public origins before serving requests.
- Database URLs in `postgres://` or `postgresql://` format automatically use the installed psycopg 3 driver. `DATABASE_SSLMODE=require` enforces encrypted internal Render connections. Render's internal database certificates are self-signed; this mode relies on the provider's private network for endpoint identity. Public database access is disabled with `ipAllowList: []`.
- Only Next.js listens on the public service port. FastAPI binds to container loopback; browser requests use the same-origin `/api` proxy. Cookies are Secure, HttpOnly, and SameSite Strict. Mutation requests still require CSRF protection. HTTPS responses include HSTS.
- Account registration requires a random invitation code. The token is not persisted in account records, exposed by the health API, or used in generated application documents.
- The container briefly starts as root to initialize a new persistent disk directory, then drops to UID/GID 10001 before starting application processes. It does not recursively change arbitrary disk contents.
- A worker heartbeat drives readiness. An exited child or a stale worker heartbeat stops all three processes so the hosting platform can restart the complete service. PostgreSQL task leases still control recovery. A stopped worker after a submission checkpoint cannot cause an automatic duplicate submission.
- An encrypted marker on the persistent disk detects an accidentally replaced encryption secret and prevents silent startup with an incompatible key.
- Auto Apply remains off by default. External final submissions remain manual because no external final-submit adapter has been authorized. The test portal is disabled. If the hosting kernel cannot provide Chromium's required sandbox for external preparation, that attempt pauses for manual completion; the sandbox is not disabled to make it work.

## Backups, recovery and updates

Render's paid PostgreSQL provides point-in-time recovery and logical exports. Render takes daily persistent-disk snapshots and retains them for at least seven days. Check actual retention and restore controls in your account. The database holds the encrypted candidate documents and browser state; the small disk holds the encryption-key continuity marker. Restore the database with its original encryption secret and a matching marker. Provider backup configuration and an actual remote restore must be verified after provisioning; the local test does not establish provider backup readiness.

For an application update, push the tested source commit and trigger a deploy explicitly; automatic deploys are disabled. Startup applies numbered database migrations under a PostgreSQL advisory lock. With a persistent disk, deploys have a short interruption. A previous source commit can be redeployed, but future schema migrations may require a forward fix rather than an application-only rollback.

The single-service arrangement is intended for one candidate or a small private workspace. It cannot scale to multiple replicas while using one attached disk. Scaling requires operating workers separately and relocating the persistent key-continuity check; candidate documents and browser state already live in shared PostgreSQL. A larger installation should move document payloads to encrypted object storage to reduce database size. Monitor the initial 1 GB database allocation and increase it when necessary. Do not delete resume versions or browser state automatically to recover space.

For emergency intervention, use the dashboard's stop button. To stop all background activity immediately, suspend the Render application service. Keep the database and disk for recovery. Deleting provider resources is a separate destructive action.

## Verification status

See `artifacts/hosting-runtime.json` and `artifacts/hosting-backend-tests.xml` for executed local checks. The Blueprint is checked against Render's published JSON Schema, and the production frontend is built with the same loopback API target as the cloud Dockerfile. The combined runtime is exercised using the existing dependency image, a read-only snapshot of current source, and the fresh frontend build. This validates runtime composition without claiming that a new cloud image or provider deployment has already been built.

Public DNS, provider TLS, provider billing, managed backup retention, and a remote deployment can only be verified after connecting the hosting account and provisioning resources. No real external internship application is submitted by these checks.
