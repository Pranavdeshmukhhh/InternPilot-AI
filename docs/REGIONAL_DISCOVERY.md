# Nearby, India and international opportunities

Both the Internship explorer and Hackathon explorer offer Everywhere, Near my cities, Across India, International, Worldwide location and Location unknown views. These filters use the same stored source records, preserve search and other filters, and paginate on the server. International means a recognized overseas location; it does not certify acceptance of Indian applicants. A plain Remote label is not worldwide eligibility.

Near my cities defaults to **Nagpur and Pune**. Choose an individual city after selecting that view. Expand **Local places & discovery coverage** to change the city list or disable nearby groups. Preferences are encrypted with the candidate profile and survive a restart. Clearing the list disables local matches. These are preferences, not a declaration that you live in those places.

Named nearby groups:

| City | Included areas when nearby groups are enabled |
| --- | --- |
| Nagpur | Nagpur, MIHAN, Butibori, Hingna, Kamptee |
| Pune | Pune/Poona, Pimpri, Chinchwad, PCMC, Hinjawadi/Hinjewadi, Wakad, Chakan, Talegaon |

Other cities match their literal names. This is a named-place filter, not geocoding, a radius calculation or a guarantee of commuting distance. Country recognition uses a conservative maintained place list and typed venue country codes. Unsupported or ambiguous locations remain unknown; not every city or country is covered. Locations can belong to both India and International if the publisher explicitly lists offices in both.

## Discovery coverage

Existing employer boards supply their published locations, the InternScan India feed supplies community references, and the MLH calendar supplies hackathon events. These sources do not guarantee listings around every city. Filters never invent opportunities to fill an empty view. Current employer availability and registration rules still need verification.

For broader public-announcement search:

1. Set `BRAVE_SEARCH_API_KEY` in the server `.env` and restart the API and worker. Keep the key server-side.
2. Open either explorer, expand Local places & discovery coverage, and review the generated queries.
3. Select **Enable regional search sources**. The current plan adds independent internship, hackathon, startup, student-role, employer-discovery and research lanes. With the default two cities there are 20 queries, including India, remote and international coverage. Repeating the action preserves existing source settings and avoids duplicates.
4. Run **Find opportunities** or leave the worker running. Newly added queries refresh every six hours with the existing queue, retries, host limits and caching. Adjust or disable individual queries under Discovery sources.

Changing local cities does not delete previously configured queries. Review old source settings and enable the newly generated queries if needed. The app does not provision or purchase a search subscription. Provider quotas and charges apply: the 20-query default at six-hour intervals can request up to 80 searches per day before failures/backoff. Older configured sources retain their schedules; disable redundant queries or increase intervals to fit your quota. See [small-employer discovery](SMALL_EMPLOYER_DISCOVERY.md) for bounded coverage and access review.

Search reads at most 20 results per query and spends at most three publisher-page reads on verification or employer-link discovery per run. Both internship JobPosting and hackathon Event metadata are supported. Employer directories have no date restriction; research programs use monthly freshness and normal opportunity searches use weekly freshness. Public destinations and robots policies are checked; restricted pages are not crawled. Search credentials are never forwarded to publisher pages.

Search snippets, search-query city names and company headquarters never establish location. References without matching publisher metadata stay unverified and location unknown, even when a search targeted Pune. Event announcements do not imply open registration. Weak references cannot replace stronger employer facts or keep a removed employer listing open. A search API cache response cannot refresh the timestamp of an employer page that was not fetched.

All existing eligibility checks remain in force: graduation year 2029 incompatibilities are rejected; unclear visa, work authorization, academic or participation rules require review. Local preference adds a small explainable ranking bonus; it never grants eligibility or submission permission.

## Validation

`backend/tests/test_geography.py` covers local/India/international separation, named nearby aliases, custom preferences, ambiguous remote metadata, pagination and bookmarks for both opportunity types, profile persistence, missing search credentials, repeat setup, account isolation, snippet-versus-official provenance, and bounded search verification using synthetic responses. Live authenticated Brave delivery requires an operator-provided API key and is not claimed as tested without it.

On 23 October 2026, the full backend suite passed 397 tests and the existing and regional browser suites passed 24 and seven checks respectively. Frontend lint/typecheck/production build and Ruff passed. Regional screenshots use explicitly labeled synthetic data in an isolated temporary database. Read-only live checks independently returned 10 Figma listings, 70 MLH announcements and 11 InternScan India references; the India feed included one local-city reference, whose employer availability remains unverified. These results do not establish a real Nagpur listing or Indian-student eligibility for overseas listings.

Reproduce from the project directory after building the frontend and stopping other services on local ports 8000/3000:

```bash
backend/.venv/bin/python scripts/run-ui-acceptance.py --regional
backend/.venv/bin/python scripts/verify-regional-discovery.py
```

The second command performs public read-only requests. The browser runner starts and stops its own temporary services and never uses the user's database. On Windows use `backend\.venv\Scripts\python.exe` instead of the Unix interpreter path.

No schema migration is needed: added preferences live inside the existing encrypted profile and region classifications are computed from stored listing metadata.
