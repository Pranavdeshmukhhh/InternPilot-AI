# Warm UI and smoother browsing

This upgrade changes the existing Next.js/FastAPI application in place. Existing source discovery, hackathons, application approvals, encrypted profiles, Gmail workflows and owner access controls remain. Schema version 5 and API response shapes are unchanged; no credentials or new dependencies are needed for these improvements.

## Appearance

New visitors start in light mode, including when their operating system prefers dark. Explicit light, dark and system preferences are preserved and applied before paint. The light palette uses ivory `#F7F6F2`, white surfaces, charcoal `#242A28`, slate `#626B66` and teal `#246A60`; the optional dark palette uses warm charcoal and muted teal. These are visual/readability choices, not claims of psychological effects.

Panels use soft 20–24px curves, controls use rounded/pill shapes, and related rows share quiet surfaces and dividers. Focus indicators, status colors, mobile touch targets, reduced motion and forced colors are supported. Existing CSS layers resolve through common palette tokens instead of competing violet/blue themes.

Screenshots contain explicitly labeled synthetic opportunities:

- [Desktop explorer](../artifacts/warm-explorer-desktop.png)
- [Mobile light](../artifacts/warm-explorer-mobile.png)
- [Mobile dark](../artifacts/warm-explorer-mobile-dark.png)

## Browsing

- Each account/explorer remembers filters, sorting, page and filter-panel state within the current browser tab. Returning to a list restores its position. Preferences contain browsing selections, not cached opportunity/profile payloads. Storage failures do not prevent browsing.
- Internships, hackathons and saved opportunities start with newest-first sorting; AI matches retain best-match sorting. Explicit saved sort preferences take precedence.
- Search waits 300ms after typing. A `/` shortcut focuses search when focus is outside a text control or dialog. Older fetches are canceled and cannot overwrite the active query/account.
- Changed queries hide old rows until the new results arrive. Calm placeholders preserve the previous list height, including after viewport resizing. Background updates of the same query keep usable rows visible.
- Pagination moves keyboard focus to the result summary. Errors clear the busy state, release preserved empty height, show unavailable results and offer a working retry.
- Live event bursts are coalesced with a two-second minimum spacing for scheduled refreshes. Concurrent workspace refreshes share one in-flight request group. Polling pauses while the tab is hidden and resumes on visibility; the existing event connection can remain open. Actions wait for an appropriately fresh snapshot before reporting completion. Session epoch checks also protect profile/policy responses.
- Opening Resume studio, Applications, Notifications or Discovery sources fetches that view again after any older workspace refresh settles. A worker-generated document cannot remain hidden solely because an earlier multi-endpoint refresh contained an empty library snapshot.

## Query work

The new `backend/app/opportunity_query.py` pushes ownership/saved visibility and safe kind, remote, company and text predicates into the database. Search keeps exact Python casefold behavior for Unicode, literal wildcard characters, missing fields and explicit nulls. Malformed remote values cannot trigger a PostgreSQL Boolean cast error.

Chronological pages without a computed-score filter scan candidate facts in 200-record scalar batches, preserve exact expiry/location/strict-qualification filtering and totals, and hydrate/evaluate only the selected page. Bookmark/application decoration is limited to selected IDs. Best-match, eligibility and recommendation requests still compute the necessary scores for correctness; numbered API pagination is retained.

The reproducible local benchmark created **10,000 synthetic opportunities** and returned a 20-item newest page in **0.470546 seconds**, with **20 matching evaluations and 20 ORM hydrations**. This is one local SQLite measurement; exact totals still scan candidates. It is not a cloud-throughput claim, an indexed-only query or a best-match benchmark. The full-list compatibility endpoint intentionally returns its full result list. Very deep numbered pages and very large best-match catalogs still need additional indexing/materialized evaluation or cursor work before claiming unbounded scale.

Evidence: [query benchmark](../artifacts/warm-query-benchmark.json), [complete backend JUnit](../artifacts/warm-query-backend-tests.xml), [browser checks](../artifacts/warm-ui.json).

## Reproduce

```bash
cd frontend
npm run build
cd ../backend
.venv/bin/python -m pytest -q
cd ..
backend/.venv/bin/python scripts/run-ui-acceptance.py --warm-ui
backend/.venv/bin/python scripts/benchmark-opportunity-query.py
```

Browser checks and the benchmark create temporary databases and synthetic accounts. No real employer application, external document upload or recruiter email is performed. On Windows use `backend\.venv\Scripts\python.exe`. Cloud deployment and source-provider credentials remain separate setup tasks.
