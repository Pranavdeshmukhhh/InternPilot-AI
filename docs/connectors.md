# Discovery and application coverage

Discovery permission and submission permission are separate. `permitted=true` on a source acknowledges read-only access for that source. It does not authorize automated job applications. Only explicitly supported adapters can submit, and every submission still passes the candidate's policy.

| Source kind | Implemented discovery method | Required configuration | Submission |
| --- | --- | --- | --- |
| `greenhouse` | Public Greenhouse Job Board API with full posting content | Company and board slug | Assisted/manual external completion |
| `lever` | Public Lever postings JSON API | Company and account slug | Assisted/manual external completion |
| `ashby` | Public Ashby job-board API, compensation when published | Company and board slug | Assisted/manual external completion |
| `smartrecruiters` | Public postings API plus cached posting details | Company identifier | Assisted/manual external completion |
| `workday` | Explicitly permitted public CXS listing endpoint | Exact `https://<tenant>.myworkdayjobs.com/wday/cxs/<tenant>/<board>/jobs` URL | Assisted/manual; authenticated/private boards unsupported |
| `html` | Public `JobPosting` and hackathon `Event` JSON-LD extraction | Permitted HTTPS page with robots access | Assisted/manual |
| `feed` | RSS/Atom announcement parsing | Permitted HTTPS feed with robots access | Assisted/manual |
| `mlh` | Official season event metadata | Optional numeric season slug; defaults to upcoming season, minimum 30 minutes | Discovery; verify registration |
| `internscan` | Published India/country active JSON API | Default India URL or published country/global active feed, minimum 15 minutes | Reference; verify employer |
| `jobspy_feed` | Authorized public CSV/JSON/JSONL export URL | Permitted HTTPS publisher URL, minimum 15 minutes | Reference; no board scraping |
| JobSpy / InternScan import | Local public-metadata file under Discovery sources | CSV/JSON/JSONL, 8 MiB / 2,000 rows | Reference; no scraper execution |
| `github_list` | Bounded SimplifyJobs references and employer-page probes | Supported repository slug; minimum 30 minutes | Partial discovery; unconfirmed URLs remain references |
| `devpost` | Disabled until a permitted access method is verified | Not a working integration | Manual |
| `search` | Brave Search API, recent results | Operator API key and query in source slug | Discovery only; verify employer and requirements |
| Local test portal | Test-only fixture postings | `TEST_MODE=true`, exact configured origin | Real Playwright submission to local authorized endpoint |
| LinkedIn, Indeed, Wellfound, Internshala, Unstop | No direct crawling or authenticated access bundled | An authorized provider/export integration must be added separately | Manual |

New accounts have real public ATS sources plus MLH and InternScan so discovery can be exercised without an API key. They are examples of supported boards, not a claim that each board currently offers an India-based 2029-compatible role. Preferred employers can be edited in the candidate profile; automatic submission has a separate company allowlist in the policy. Add their permitted official feed, ATS board or JSON-LD page when available.

All source requests use an identifying user agent, HTTPS public destinations, DNS/IP checks, bounded response sizes, explicit redirect validation, conditional `ETag`/`Last-Modified` requests when available and host-level rate limiting. 401/403 errors stop access attempts; 429 honors a retry delay. There is no login harvesting, CAPTCHA solver, rotating proxy evasion or authentication bypass.

Feeds/pages respect robots access. Dynamic career pages without supported structured data report an unsupported-source error rather than fabricated listings. Workday listing metadata has no full requirement text, so eligibility cannot become verified from that response alone. Current SmartRecruiters and Workday discovery caps are marked as truncated when applicable; operators should choose narrow sources or implement pagination for large boards.

Each normalized record retains its official application URL, description, extracted requirement evidence, publication date when actually known, first discovery and last verification. Greenhouse's update timestamp is not treated as the original publication date. Lever's creation timestamp is retained as source metadata, not presented as a verified publication date. Deduplication strips common tracking parameters while preserving requisition identity.

Search snippets and broad university announcements can be useful leads but are incomplete evidence. Review their official source before applying. Source configuration never grants permission to violate a platform's access rules.

See [current upgrade results](UPGRADE_REPORT.md) for live-tested sources, scheduled refresh limits and repository/license audits. Event timestamps do not establish a registration deadline; aggregator links do not establish employer verification.
