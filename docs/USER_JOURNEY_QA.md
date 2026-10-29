# User journey verification — 29 October 2026

Executed the production frontend with a real Chromium browser, FastAPI, an isolated
SQLite database and an application-only background worker. No real account data,
provider credentials, external applications or emails were used. The test portal
actually received an uploaded PDF and returned a confirmation; the demo is explicitly
labeled synthetic. These checks do not certify Windows, cloud deployment, live
employer integrations, or production PostgreSQL capacity.

Environment: Linux x86_64, Python 3.12.14, Node 24.19.0, Next.js 15.5.28,
Chromium 151.0.7922.173. The new local worker journey is also included in the
frontend CI job with its own uploaded artifacts; hosted CI was not run here.

## Confirmed defects corrected

1. **Session-service outage looked like logout.**
   `frontend/src/features/workspace/provider.tsx::SessionProvider` discarded every
   startup exception, and `workspace.tsx::Workspace` redirected an absent session
   to `/login`. With an otherwise valid session cookie, a controlled 503 on
   `/api/auth/session` reproduced the incorrect login page. The provider now
   distinguishes an unauthenticated 401 from a service/network failure, cancels
   abandoned checks, and exposes an explicit retry state. The workspace retains
   its URL, does not render private content without successful authentication,
   and recovers the same account through Retry. Logout and invalid-password
   rejection remain verified.

2. **Live application updates were buffered for almost a minute.**
   `backend/app/main.py::stream_events` lacked `Cache-Control: no-transform`.
   Additionally, `security_headers` overwrote endpoint cache directives with
   `no-store`, so adding the stream header alone did not fix the defect. Through
   the actual Next.js proxy, the first stream event exceeded a five-second test
   deadline, and the confirmed application became visible after **59.500 s**.
   The stream now sends `private, no-cache, no-store, no-transform`; middleware
   preserves those directives while enforcing `no-store`. In the final local
   run the ready event arrived in **20.5 ms**, without content encoding, and
   clicking the demonstration action through visible confirmation took
   **7.948 s** including queue dispatch, PDF preparation and browser execution.
   These are individual local observations, not production latency guarantees.

The initial backend check caught the middleware overwrite (30 passed, one failed).
After the complete correction, the same 31-test selection passed. Early browser
driver attempts also needed route and alert-selector corrections; those were
test-harness errors, not product defects.

No schema or stored-data change is required for these two fixes. They can be
rolled back as code/configuration changes with the current database and encryption
key retained; doing so restores the observed outage/update defects.

## Reproduction

Install locked dependencies and build the frontend first. These commands use
Linux paths; use the Python installed inside Docker/WSL for Windows.

```sh
cd frontend
npm ci
npm run build
npm run lint
npm run typecheck
npm test
npm run format:check
cd ..
UI_ARTIFACT_DIR=artifacts/user-check/journey backend/.venv/bin/python scripts/run-ui-acceptance.py --user-journey
UI_ARTIFACT_DIR=artifacts/user-check/workspace backend/.venv/bin/python scripts/run-ui-acceptance.py --phase6-ui
UI_ARTIFACT_DIR=artifacts/user-check/access backend/.venv/bin/python scripts/run-ui-acceptance.py --access-ui
UI_ARTIFACT_DIR=artifacts/user-check/founder backend/.venv/bin/python scripts/run-ui-acceptance.py --founder-ui
cd backend
.venv/bin/python -m pytest tests/test_api_worker.py tests/test_catalog_startup.py tests/test_worker_reliability.py -q --junitxml=../artifacts/user-check/backend.xml
```

The UI runner refuses occupied ports 3000/8000, creates temporary data and encryption
keys, clears notification/model credentials, and stops its processes afterward.
`--user-journey` enables only the application worker role with concurrency one;
it never starts discovery or outreach workers. Run the browser commands sequentially.
The access/founder drivers now also honor `UI_ARTIFACT_DIR` instead of overwriting
historical evidence.

## Executed results

- Backend selection: **31 passed**, 67.44 s, no skips. Includes actual worker
  submission/upload/screenshot/confirmation, duplicate prevention, crash recovery,
  tenant isolation, legacy catalog startup and stream headers. JUnit:
  `artifacts/user-check/backend.xml`.
- Application browser journey: **10 grouped checks passed**, no uncaught JavaScript
  errors. Includes honest empty history, API outage/retry, prompt stream delivery,
  local submission and PDF hash verification, duplicate protection, persistence,
  mobile overflow, session outage/retry, logout and wrong/correct-password login.
  Evidence: `artifacts/user-check/journey/report.json`.
- Frontend production build, ESLint, TypeScript, formatting and both Node test
  files passed. The existing Next.js ESLint-plugin notice is still emitted by
  the build. Backend Ruff and `git diff --check` passed.
- Final workspace rerun: **20 grouped checks passed**, no uncaught JavaScript
  errors; automated accessibility gates passed on the checked screens in both
  themes, with layouts exercised from 320–1920px. Invitation/Terms rerun:
  **5 groups passed**. Founder recovery/MFA/private-report rerun: **4 groups
  passed**. Combined with the worker journey: **39 browser check groups**.
  Screenshots under `artifacts/user-check/` show isolated synthetic records only.

## Remaining limits

The missing React Query dependency in the user's earlier screenshot requires
installing the current lockfile (`npm ci` inside `frontend`) and restarting the
old dev process, or using the integrated Docker quickstart. This environment's
installed package and production build work; the user's Windows installation
was not remotely changed. The earlier catalog-indexing fix remains in this
release and its legacy-data regression ran again successfully.

Gmail/notification delivery, third-party submissions, external source freshness,
Windows Docker builds and public private-workspace deployment were not tested
here. No new deployment, real founder credentials, or GitHub push is claimed.
Existing production security/capacity gates remain documented in
`SECURITY_REVIEW.md` and `PERFORMANCE_REPORT.md`.
