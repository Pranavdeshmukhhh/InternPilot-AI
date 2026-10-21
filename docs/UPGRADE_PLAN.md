# Internship and hackathon upgrade

## Existing implementation inspected

The application is an existing Next.js 15/React/TypeScript frontend with Tailwind and Radix components, a FastAPI/Pydantic backend, SQLAlchemy/PostgreSQL with a SQLite local fallback, a durable database worker queue, optional Redis wakeups, and Playwright. Candidate facts, documents and browser state are encrypted. Existing files include `backend/app/discovery.py`, `matching.py`, `services.py`, `worker.py`, `automation.py`, `documents.py`, and the connected frontend under `frontend/src/`.

The working ATS API readers, evidence-based internship matching, actual PDF generation, encrypted storage, authenticated dashboard, duplicate protection and conservative restart recovery are preserved. Before the hackathon extension, the current backend regression run passed 256 tests and the frontend production build passed.

Gaps found: internship-specific normalization and filters; no hackathon-specific eligibility path; no saved-opportunity persistence; no dedicated recommended/saved/hackathon views; no configurable delivery adapters or quiet hours; no source-change alerts for bookmarks; list endpoints lacked pagination; external document preparation lacked a separate per-upload consent checkpoint. Earlier upgrades added account recovery, actual worker health, automatic factual drafts, and deadline alerts.

## Source research

See `research/hackathon-repositories.md` and `research/internship-repositories.md` for pinned source files, licenses, maintenance evidence and static defects in all six requested repositories. Public source was inspected without executing it. Approaches are reused conceptually; source code with missing or incomplete license terms is not copied. No unsupported endpoint or alerting feature is presumed to work.

## Implementation order

1. Preserve and regression-test existing discovery, profile, matching, documents and local browser demonstration.
2. Add additive database migrations for bookmarks, notification settings/outbox, and specific upload consent.
3. Normalize internship and hackathon records while keeping registration deadlines separate from event dates. Add live-checked public sources; retain restricted sources as explicitly unavailable.
4. Add deterministic hackathon eligibility/relevance before optional model interpretation. Display unknown eligibility and missing information honestly.
5. Add paginated search, saved/recommended views, bookmarks, source-change alerts, and complete notification controls.
6. Keep outbound channel messages as drafts requiring approval for the exact message and recipient. Enforce quiet hours and durable duplicate/checkpoint handling.
7. Add dark/light/system themes and accessible responsive views without replacing the current framework or design.
8. Run backend tests, build/type checks/lint, real read-only ingestion, browser workflows, persistence/restart checks, and protected local submission tests. Package source and report verified limits.

Git publishing and hosting work have been stopped at the user's request. All application submission demonstrations use the authorized local test endpoint. There are no real employer submissions or outgoing messages during validation.
