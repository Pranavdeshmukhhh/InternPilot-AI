# Invitation-only workspace and Terms update

2026-10-29. The landing/demo remain public, as requested. The public Terms page now has a compact section index, sticky desktop navigation, smooth anchor scrolling and short movement transitions. Text stays fully opaque: an intermittent contrast failure during the original fade was caught and corrected. Reduced-motion users get immediate transitions and normal scrolling; mobile uses a two-column section index without overflow.

## Who can sign in

The full application has a real email/password login at `/login`. New accounts require an **owner-issued, email-bound, single-use invitation**, expiring after seven days by default (API supports 1–7). Invitations do not grant owner privileges. Existing enabled accounts continue working; the owner can disable an account to revoke sessions and stop its automation, or re-enable it through existing controls. This update does not silently disable or delete historical users.

`INVITATION_ONLY=true` is the default and mandatory in production. `INVITATION_ONLY=false` is a development/test compatibility mode; production validation rejects it. A legacy shared `REGISTRATION_TOKEN` cannot bypass an individual invitation when invitation-only mode is enabled. `ALLOW_REGISTRATION=false` pauses **all** new activation, even with a valid invitation; existing sign-in still works.

### First owner

Local Docker, including Windows 11 PowerShell:

```sh
docker compose exec backend python -m app.admin create-owner
```

The CLI asks for email and hidden password/confirmation; no default/master password is created. For an existing account, use `python -m app.admin grant-owner` inside the backend container instead, retaining its password. Native development runs those commands from `backend` with its virtual environment.

Cloud Compose uses `api` instead of `backend`:

```sh
docker compose --env-file .env.cloud -f deploy/compose.cloud.yaml exec api python -m app.admin create-owner
```

Keep the existing database/encryption key. Do not run these commands against an unrelated deployment.

### Authorize someone

1. Set `INVITATION_ONLY=true` and `ALLOW_REGISTRATION=true` in the account backend configuration, recreate the API container, then sign in as the named owner. The cloud template keeps activation closed until explicitly enabled.
2. Open **Owner → Workspace invitations**. Enter the person's email, confirm your owner password and check the authorization box.
3. Create the invitation and copy the displayed link. It is shown once; share it privately yourself. No email is sent automatically. Maximum 100 unexpired, unused invitations per owner.
4. The recipient opens the link at the actual workspace host, enters that exact email and chooses their own password. The code is carried in a URL fragment, not a server query, and removed after reading. If they refresh before activation, reopen the original invitation link.
5. Revoke unused invitations from the same panel with fresh password/consent. Used invitations cannot be replayed. For an activated account, use **Accounts → Disable account** instead. Owner Refresh reloads invitations without retaining a displayed bearer link.

## Persistence and compatibility

No schema change: invitation records use a dedicated `account-invite:` namespace in the existing durable `coordination_state` table. This namespace is outside auth-window cleanup. It stores the token **digest**, encrypted recipient email, email digest, issuing owner, timestamps and status; raw invitation tokens are not persisted. List responses exclude token digests/secrets, are owner-authorized, and return at most 100 of that owner's records with active pending invitations first. The registration payload retains the existing `registration_token` field.

The registration transaction locks the existing invite row, verifies email/secret/expiry, marks it consumed, creates the user and commits the session together. A write lock serializes SQLite callers; PostgreSQL also holds the row lock. Existing unique `users.email_hash` remains a second duplicate guard. Failed account creation rolls back consumption. Invalid codes create no coordination rows. Owner issuance/revocation require RBAC, CSRF, current-password verification, explicit consent and shared admission limits; audit events contain no raw invite secrets. Recipients prove possession of the private link, not independently verified mailbox ownership.

No user data is removed. Invitation metadata/audit retention follows the current installation's retention limitations; no new automatic erasure guarantee is made. This lightweight store suits owner-managed access; a dedicated indexed invitation table is a future option for large organization histories, not necessary for this bounded change.

**Safe rollout/rollback:** close activation (`ALLOW_REGISTRATION=false`) before upgrading all API instances. Do not mix old open-registration writers with new invitation-only writers. Preserve keys/DB and upgrade the matching frontend; then reopen activation with invitation-only mode. Rollback first closes activation and stops writers, then returns to the prior matching image. Leave invitation rows intact; old code ignores them. Never reopen legacy unrestricted registration during rollback. Existing approved users can still sign in while activation is closed.

## Public deployment boundary

Live Terms: https://internpilot-ai-notebook.antigravityfree101.chatgpt.site/terms

Public sign-in entry: https://internpilot-ai-notebook.antigravityfree101.chatgpt.site/login

The connected Sites host still serves **static public pages only**. Its `/login` page truthfully explains invitation-only access and the undeployed account backend; it collects no credentials. The real account UI/API and owner invitations were implemented and exercised locally. Do not claim the backend has been deployed. No native Sites audience restriction was applied: landing/demo remain public.

After deploying the full stack through DEPLOYMENT.md, optionally set build-time `PUBLIC_WORKSPACE_URL` to its real exact HTTPS origin and re-export/redeploy the public pages. The public sign-in entry will offer a top-level link to that host's `/login`. The value cannot contain userinfo/path/query/fragment and cannot equal the public Site origin (redirect loop prevention). No URL is invented here.

Final static deployment version 5: source commit `90f5ceb9264f60399f2261010b48bc409c122aa8`; deployment `appgdep_6ae2d8a96e80819193d3b9b9049e94d1`, terminal `succeeded` at 05:25:16 UTC. [Machine-readable record](../artifacts/access-update/deployment.json). The interim version 4 was superseded after correcting the motion contrast finding. Previous public version 3 remains available for static rollback; workspace policies/data are independent of that rollback.

## Verification

- Targeted real API regressions: **44 passed** (invitations, owner access, hosting configuration, account/session security).
- Full isolated SQLite regression: **538 passed, 2 skipped**, one existing deprecation warning, 221.23s pytest time. PostgreSQL-only planner/locking variants were not enabled. [Result](../artifacts/access-update/backend.json), [JUnit](../artifacts/access-update/backend.xml).
- Five grouped browser checks exercise actual owner issuance, wrong-email rejection, activation, lack of member owner privileges, revocation, fragment handling, Terms anchors/responsiveness/reduced motion. Four Terms/login axe theme evaluations reported zero violations. [UI evidence](../artifacts/access-update/ui/report.json).
- Exact static-export checks cover the public demo, safe sign-in page with no email/password form, private route absence and API isolation. [Report](../artifacts/access-update/static/report.json). Build/types/lint/format, five frontend unit tests and OpenAPI contract generation/drift checks passed. CI includes the new access browser suite; hosted CI was not executed here.
- Published HTTPS pages/assets are independently checked against export hashes: [live HTTP report](../artifacts/access-update/live-http.json). Live Chromium remains limited by the managed proxy CA described in PHASE9_LAUNCH; no trust change or TLS bypass was attempted.

Reproduce with `python scripts/verify-backend.py --output-prefix artifacts/access-update/backend -- -q -ra`, then `npm --prefix frontend run build` and `python scripts/run-ui-acceptance.py --access-ui` using the backend environment. The browser runner creates isolated synthetic data, suppresses provider credentials and starts no crawlers or email workers.
