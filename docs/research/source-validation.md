# Public opportunity source validation

Live checks ran **2026-10-21, 07:10:56–07:11:09 UTC** through the existing bounded HTTPS client, inherited proxy, public-destination checks, host throttling and robots enforcement. These were public reads only. No registration, application, login, message or personal-document upload occurred.

The [timestamped JSON observation artifact](source-validation.json) records source counts, sample URLs, verification outcomes and diagnostic limits.

| Source | Observed result | Implemented behavior |
| --- | --- | --- |
| [Official MLH 2027 calendar](https://www.mlh.com/seasons/2027/events) | HTTP 200. Publisher metadata contained 69 upcoming records, including one canceled event. **68 events normalized** at 07:11:04 UTC. | `mlh`: enabled only with source permission; reads public embedded calendar JSON and excludes canceled/ended/draft entries. Calendar membership confirms a listing, without confirming participant eligibility, registration availability or organizer deadlines. |
| [SimplifyJobs Summer2027 reference](https://github.com/SimplifyJobs/Summer2027-Internships) through the [GitHub public contents API](https://api.github.com/repos/SimplifyJobs/Summer2027-Internships/contents/README.md) | HTTP 200. **1,763 distinct canonical employer application links** were extracted from the current public README. The diagnostic checked three employer pages; **zero acquired matching verified JobPosting metadata**. All three remained explicitly unverified at 07:11:09 UTC. | `github_list`: optional attributed link discovery. Retains only title, company and canonical application URL from the README; independently reads permitted official pages for any richer facts. Runtime checks at most 20 links per scan and marks larger results partial. No repository code, bulk listing JSON or dataset descriptions were copied. |
| [Devpost robots](https://devpost.com/robots.txt) | HTTP 200; generic agents were allowed. A published API with verified reuse/access permission was not established. `/terms` returned HTTP 404; that does not establish that no terms apply. | `devpost`: explicitly unsupported until a permission-verified published API or authorized feed is available. The connector raises a clear error and performs no page scraping or API probes. |

MLH's legacy `https://mlh.io/seasons/2027/events` redirects to its official `www.mlh.com` domain. The connector normalizes configured official season URLs to that domain. [Robots](https://www.mlh.com/robots.txt) allowed the season path. [Terms](https://www.mlh.com/terms) were accessible and grant limited personal, noncommercial access/use; they do not grant general republication rights. Only minimal event facts and source links are normalized here, without copying page assets or event descriptions. Broader commercial use requires separate permission assessment.

Examples observed on the MLH calendar:

| Event | Publisher listing | Publisher start time | Registration deadline |
| --- | --- | --- | --- |
| Cal Hacks 13.0 | [MLH event](https://www.mlh.com/events/cal-hacks-13-0/prizes) | 2026-10-23 17:00 UTC | Unknown |
| SBUHacks | [MLH event](https://www.mlh.com/events/sbuhacks-5f/prizes) | 2026-10-23 22:30 UTC | Unknown |
| OxHack '26 | [MLH event](https://www.mlh.com/events/oxhack-26/prizes) | 2026-10-24 01:11:11 UTC | Unknown |

The event start/end dates are stored separately from registration deadlines. Calendar location is a venue fact, not a geographic eligibility rule. Unknown organizer, prizes, fees, team-size rules and eligibility remain unknown. An advertised organizer website is preserved separately and is not described as verified registration access.

The three sampled repository references were:

- [Bosch: Calibration Process Optimization Intern](https://jobs.smartrecruiters.com/BoschGroup/744000156585075)
- [LinkedIn: Software Engineer Intern](https://jobs.smartrecruiters.com/LinkedIn3/744000156616169)
- [DriveWealth: AI Consulting Associate Program Product Owner Intern](https://boards.greenhouse.io/drivewealth/jobs/8038087003)

Their linked pages responded, but the connector could not confirm matching public JobPosting metadata. A 200 response or a community list entry alone does not establish an open role. No eligibility, deadline, posting date or compensation was inferred from these references. The three-link diagnostic limit was temporary; the implementation's limit is 20. These counts measure source references and checks, not verified open internships.

The [repository license review](internship-repositories.md) found no verified reuse license for Simplify's repository data or scripts. This connector independently parses minimal attributed public references and does not enable bulk dataset ingestion. On README HTTP 304, individual sampled employer pages are still checked again; a cached community list cannot refresh an employer verification silently. Robots denial, 403, rate limiting, private destinations and missing/mismatched official metadata remain unverified or fail closed; no alternate access path is attempted.

No access claim was established for Devfolio, Unstop, HackerEarth or DoraHacks. They are not enabled by this connector. An authorized feed or permitted public structured page can be configured through the platform's separate generic connectors.

Validation command: `.venv/bin/python -m pytest tests/test_opportunity_sources.py tests/test_discovery.py -q` from `backend/`: **41 passed**. Tests cover canonical links, source permission, robots-mode requests, conditional caching, canceled events, missing deadlines, malformed schemas, repository attribution, company continuation rows, private/aggregator rejection, bounded work, independently verified metadata, and explicit unsupported Devpost behavior. Automated tests replace network boundaries; the live observations above were separate real reads.
