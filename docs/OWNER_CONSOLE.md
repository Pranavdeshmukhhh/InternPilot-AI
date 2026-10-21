# Your owner login

There is no shared master password or hidden sign-in route. An installation owner is a named account that you create or promote using a command on your own machine. Sign in normally afterward and the **Owner console** appears in navigation. Public registration always creates an ordinary member; the first visitor does not become an owner.

## Windows / Docker Desktop

Start the application, then open PowerShell in the project folder.

If you already registered your account:

```powershell
.\scripts\owner.ps1 -Task grant
```

Enter your registered email when prompted. Your password stays the same. The command signs out existing sessions so you must sign in again.

To create a separate owner account:

```powershell
.\scripts\owner.ps1 -Task create
```

Enter your email and choose a password of at least 12 characters at the hidden prompts. The password is hashed with scrypt. It is not printed, placed in arguments, added to `.env`, or saved in the source archive. Existing accounts are never overwritten by this command.

Equivalent direct commands:

```powershell
docker compose exec backend python -m app.admin grant-owner
docker compose exec backend python -m app.admin create-owner
```

For native development, use the same configured backend environment as the running API:

```powershell
cd backend
.venv\Scripts\python.exe -m app.admin create-owner
```

On Linux/macOS the executable is `.venv/bin/python`.

## What you can manage

- Actual database table counts and active-session totals.
- Registered accounts with their email, account ID, access role, creation time, last sign-in and most recent authenticated visit. Last-seen updates are limited to once every five minutes. Anonymous visitors and external career-site users are not tracked or identified.
- Candidate profile records, recent applications, document metadata and discovery sources. Record inspection requires your current owner password, a reason, and confirmation. Views show up to 200 recent applications and documents.
- Stored documents through separately approved, audited downloads.
- Member enable/disable controls. Disabling revokes sessions and pauses automation. Enabling restores login only; it does not silently resume applications.
- Member session revocation and replacement-password resets. Resets revoke sessions and activate emergency stop. Share replacement passwords privately and ask account holders to change them.
- An owner audit trail. Affected members also receive an in-app owner-access notice. The sign-up page discloses that installation owners can administer account records.

Owner accounts cannot disable/reset each other through the browser. Manage your own password under Account security, or use the trusted local recovery command:

```powershell
.\scripts\owner.ps1 -Task reset
```

## Password and credential limits

Original passwords cannot be retrieved: only salted scrypt hashes exist. The console returns neither passwords nor hashes, session tokens, browser authentication state, provider keys, encryption keys, or the private custom-answer vault. There is no arbitrary SQL execution endpoint. Owner authority is checked on the server, independently of menu visibility; sensitive actions recheck your current password and require CSRF protection.

Keep owner access limited to trusted operators. Never use a shared default login or commit passwords. Your owner account has administrative access to personal records; access reasons are audited and must not contain passwords. There is no owner account automatically provisioned in the downloadable archive.

## Visual update

The interface now uses warm paper backgrounds, deep blue text and controls, serif page headings, rounded navigation and buttons, curved panels and quieter list layouts. Decorative orbs, promotional kickers and the AI brand badge were removed. Metrics share a single ledger instead of four separate floating cards. Dark mode uses matching navy surfaces with readable text. Functional status indicators and the verified-profile progress ring remain.

Existing discovery, matching, saved items, application checks, consent controls, themes and mobile navigation remain connected to the same backend.
