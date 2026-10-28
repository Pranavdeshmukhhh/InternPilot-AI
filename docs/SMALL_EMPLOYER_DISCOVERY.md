# Finding opportunities beyond large employers

This upgrade modifies the existing discovery/worker pipeline and keeps schema version 5, saved profiles, applications, hackathons and source permissions intact. No listings or employer lists are hardcoded to make the feed appear populated.

## What changed

- Default search coverage grows from eight narrow queries to 20 independent lanes: Nagpur/Pune internships, hackathons, student roles, startup opportunities, incubator/employer discovery and university programs, plus India, remote and international lanes. Custom local cities remain editable. The plan is bounded at 64 queries across up to 20 cities.
- Searches recognize alternate titles such as project intern, student developer, research assistant, summer student and technical trainee. Trainee/assistant titles do not establish current-undergraduate eligibility and require review.
- Employer discovery searches use no publication-date restriction because older incubator/portfolio pages remain useful. Research searches use a month; ordinary opportunity searches use a week. None of these filters certifies when a listing was published.
- Publisher pages can supply actual ATS boards, RSS/Atom feeds and careers/program links. Known ATS job URLs map to their actual board slug; no slugs, companies, contact addresses or vacancies are guessed. Boards/feeds are prioritized and existing career parents suppress per-job source clutter.
- Careers pages without JSON-LD can yield labeled, unverified opportunity references from actual links. Only up to three same-origin linked opportunities are read per scan, with public-destination and robots checks. Structured publisher data can verify a reference; a plain link cannot establish location, requirements, deadline or current availability.
- A source-review queue deduplicates discoveries across owned sources. It shows the publisher evidence, requires read-only access permission before enabling, revalidates public destinations, and supports persistent dismissal. Installing a source does not claim it has responded or has vacancies.
- Scheduling interleaves owners and new/low-volume/established source groups. Existing retries do not consume scheduling slots repeatedly. Disabled accounts, emergency stops, future backoffs and active jobs remain respected. Observed source volume is not a claim about employer size.
- Search snippets are separated from publisher descriptions and cannot establish graduation requirements. Older unverified search rows also receive this protection. Weak HTML references cannot overwrite verified ATS facts. A careers-index 304 response does not refresh independently fetched child-page verification dates. Source-cache writes serialize with dismissals on PostgreSQL.

## Enable it

1. Configure `BRAVE_SEARCH_API_KEY` server-side and restart API/crawler processes. Without a key, existing public ATS feeds and explicitly configured permitted publisher pages still work.
2. Open an explorer → **Local places & discovery coverage** → review queries → **Enable regional search sources**. Existing source settings are preserved; repeated setup is idempotent. Disable older redundant queries if desired.
3. Run discovery or leave the persistent crawler running. Review **New employer & program sources**, open publisher evidence, and enable sources whose identity and automated-access permission you have checked. Failed or unsupported sources remain visible in source health.

New queries run every six hours by default. Twenty enabled queries imply up to 80 search-provider requests/day before retries; at the 64-query bound, up to 256/day. Existing sources keep their previous schedules. Provider quotas/pricing still apply. Each query receives at most 20 results and spends at most three publisher-read attempts; robots requests are additional HTTP requests. The separate scheduler/source concurrency and host budgets still apply. This is bounded search discovery, not an exhaustive crawl of every Indian company.

## Verification and limits

The source-review browser suite tests actual API installation/dismissal, consent, reload persistence and light/dark layouts at 390/768/1024px using labeled synthetic data. The regional browser suite was rerun. See [test report](TEST_REPORT.md), [new browser results](../artifacts/source-discovery-ui.json) and [live publisher snapshot](../artifacts/employer-discovery-live.json).

A live read-only Sarvam AI careers-page scan found two publisher-metadata-backed **marketing** internships in Bengaluru and the linked Ashby board. This validates publisher link/metadata extraction, not technical-role availability, small-employer identity, Nagpur/Pune vacancies or candidate eligibility. No new source was enabled in a user account by this check.

Authenticated Brave searches were tested with mocked responses because no search key was configured. Small-employer, incubator and university query coverage is implemented but live search results are not claimed. HTML without usable links/metadata, PDF-only notices, unsupported JavaScript pages and restricted platforms need manual review or a permitted feed. New sources require access review; the system does not auto-grant crawl permission. No external application, personal-document upload or recruiter message was sent.

Reproduce after installing dependencies and building the frontend:

```bash
cd backend
.venv/bin/python -m pytest -q
cd ..
backend/.venv/bin/python scripts/run-ui-acceptance.py --source-discovery-ui
backend/.venv/bin/python scripts/run-ui-acceptance.py --regional
backend/.venv/bin/python scripts/verify-employer-discovery.py
```

The final command makes permitted read-only public requests; the browser runners use temporary databases. On Windows use `backend\.venv\Scripts\python.exe`. External browser preparation still requires an OS-supported Chromium sandbox; its local-fixture test explicitly substitutes a test-only loopback launch in root/container CI, while a separate test verifies there is no production fallback.
