"""Independent public calendar and attributed link-reference connectors.

Only publisher-supplied facts are normalized. No forms, registration endpoints,
personal documents, credentials, or third-party repository code are used.
"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx

from . import discovery as safe

SUPPORTED_KINDS = frozenset({"mlh", "github_list", "devpost"})
GITHUB_REPOSITORY = "SimplifyJobs/Summer2027-Internships"
GITHUB_README = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/contents/README.md"
GITHUB_ATTRIBUTION = f"https://github.com/{GITHUB_REPOSITORY}"
MAX_GITHUB_LINKS = 20


def _headers(cache, accept):
    headers = {"User-Agent":safe.USER_AGENT, "Accept":accept}
    if cache.get("etag"):
        headers["If-None-Match"] = cache["etag"]
    if cache.get("last_modified"):
        headers["If-Modified-Since"] = cache["last_modified"]
    return headers


def _cache(response, old):
    return {"etag":response.headers.get("etag") or old.get("etag"),
            "last_modified":response.headers.get("last-modified") or old.get("last_modified"),
            "checked_at":datetime.now(timezone.utc).isoformat()}


def _public_link(value, base=None):
    if not isinstance(value, str) or not value.strip():
        return None
    url = urljoin(base, value.strip()) if base else value.strip()
    try:
        safe._syntax_url(url)
    except safe.DiscoveryError:
        return None
    return safe.canonical_url(url)


class _CalendarPage(HTMLParser):
    """Read MLH's publicly rendered Inertia JSON, without loading page scripts."""
    def __init__(self):
        super().__init__()
        self.active = False
        self.parts = []
        self.payload = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script" and attrs.get("type") == "application/json" and attrs.get("data-page") == "app":
            self.active, self.parts = True, []
        if "data-page" in attrs and attrs["data-page"].lstrip().startswith("{"):
            self._decode(attrs["data-page"])

    def handle_data(self, value):
        if self.active:
            self.parts.append(value)

    def handle_endtag(self, tag):
        if tag == "script" and self.active:
            self.active = False
            self._decode("".join(self.parts))

    def _decode(self, value):
        try:
            payload = json.loads(value)
            if isinstance(payload, dict) and isinstance(payload.get("props", {}).get("upcomingEvents"), list):
                self.payload = payload
        except (ValueError, TypeError, AttributeError):
            pass


def _season_url(source):
    season = source.get("slug") or ""
    if source.get("url"):
        parsed = urlsplit(source["url"])
        match = re.fullmatch(r"/seasons/(20\d{2})/events/?", parsed.path)
        if (parsed.scheme != "https" or parsed.netloc.lower() not in {"mlh.io", "www.mlh.io", "mlh.com", "www.mlh.com"}
                or parsed.query or parsed.fragment or not match):
            raise safe.DiscoveryError("MLH requires an official HTTPS /seasons/YYYY/events calendar URL.")
        season = match.group(1)
    if not season:
        current = datetime.now(timezone.utc)
        season = str(current.year + (current.month >= 8))
    if not re.fullmatch(r"20\d{2}", season):
        raise safe.DiscoveryError("Use the four-digit MLH season, for example 2027.")
    return f"https://www.mlh.com/seasons/{season}/events", season


def _mlh_jobs(text, url, season):
    parser = _CalendarPage()
    parser.feed(text)
    if parser.payload is None:
        raise safe.DiscoveryError("MLH's public calendar schema is unavailable; no events were invented.")
    jobs = {}
    for value in parser.payload["props"]["upcomingEvents"]:
        if not isinstance(value, dict) or value.get("status") in {"canceled", "cancelled", "ended", "deleted", "draft"}:
            continue
        title = str(value.get("name") or "").strip()
        event_url = _public_link(value.get("url"), url)
        if not title or not event_url or urlsplit(event_url).hostname not in {"www.mlh.com", "mlh.com", "mlh.io", "www.mlh.io"}:
            continue
        starts, ends = safe._iso(value.get("startsAt")), safe._iso(value.get("endsAt"))
        # Event dates are not registration deadlines or eligibility evidence.
        description = f"Listed on the official MLH {season} season calendar."
        if starts:
            description += f" Event starts {starts}."
        description += " Registration deadline, prizes, and participation eligibility require organizer verification."
        requirements = safe.extract_requirements("")
        jobs[event_url] = {
            "external_id":str(value.get("id") or event_url), "opportunity_type":"hackathon",
            "title":title, "company":"MLH member event", "organizer":None,
            "location":str(value.get("location") or "Not specified"),
            "remote":value.get("formatType") in {"digital", "virtual", "online"},
            "url":event_url, "official_url":_public_link(value.get("websiteUrl")),
            "description":description, "skills":[], "requirements":requirements,
            "published_at":None, "deadline":None, "compensation":None,
            "starts_at":starts, "ends_at":ends, "format_type":value.get("formatType"),
            "venue_country":(value.get("venueAddress") or {}).get("country"),
            "source_url":url, "source":"mlh", "verification_status":"source_verified",
            "registration_status":"unknown", "application_url_verified":False,
            "verification_note":"The official calendar confirms this event listing; registration and eligibility have not been verified.",
        }
    return list(jobs.values())


class _ReferenceTable(HTMLParser):
    """Extract only factual company/title and non-aggregator application links."""
    def __init__(self):
        super().__init__()
        self.cells = []
        self.cell = None
        self.rows = []
        self.last_company = ""

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.cells = []
        elif tag == "td":
            self.cell = {"text":[], "links":[]}
        elif tag == "a" and self.cell is not None:
            self.cell["links"].append(dict(attrs).get("href", ""))
        elif tag == "br" and self.cell is not None:
            self.cell["text"].append(" ")

    def handle_data(self, data):
        if self.cell is not None:
            self.cell["text"].append(data)

    def handle_endtag(self, tag):
        if tag == "td" and self.cell is not None:
            self.cells.append(self.cell)
            self.cell = None
        elif tag == "tr" and len(self.cells) >= 4:
            company = " ".join("".join(self.cells[0]["text"]).split())
            if company in {"↳", "↪", ""}:
                company = self.last_company
            else:
                company = re.sub(r"^[^\w]+", "", company)
                self.last_company = company
            title = " ".join("".join(self.cells[1]["text"]).split())
            self.rows.append((company, title, self.cells[3]["links"]))


def _github_references(text):
    parser = _ReferenceTable()
    parser.feed(text)
    rows = parser.rows
    # Older publisher versions use Markdown tables rather than HTML tables.
    if not rows:
        last_company = ""
        for line in text.splitlines():
            if not line.lstrip().startswith("|"):
                continue
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) < 4:
                continue
            company = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", cells[0]).strip("* ")
            if company in {"↳", "↪", ""}:
                company = last_company
            else:
                last_company = company
            rows.append((company, cells[1], re.findall(r"\[[^]]*\]\((https://[^\s)]+)\)", cells[3])))
    references = {}
    for company, title, links in rows:
        if not company or not safe.INTERNSHIP.search(title):
            continue
        for value in links:
            link = _public_link(value)
            if not link:
                continue
            host = urlsplit(link).hostname
            if any(host == blocked or host.endswith("." + blocked) for blocked in {"simplify.jobs", "github.com", "githubusercontent.com"}):
                continue
            references[link] = {"company":company[:250], "title":title[:500], "url":link}
            break
    if not references and not rows:
        raise safe.DiscoveryError("The repository's public link table schema is unavailable.")
    return list(references.values())


async def _verify_reference(client, reference):
    url = reference["url"]
    requirements = safe.extract_requirements("")
    job = {
        "external_id":url, "opportunity_type":"internship", "title":reference["title"],
        "company":reference["company"], "url":url, "location":"Not specified", "remote":False,
        "description":"", "skills":[], "requirements":requirements, "published_at":None,
        "deadline":None, "compensation":None, "source":"github_list", "source_url":GITHUB_ATTRIBUTION,
        "attribution":"Link reference: SimplifyJobs / Pitt CSC Summer 2027 list. Repository reuse license was not verified; no dataset descriptions or source code were copied.",
        "verification_status":"unverified", "verification_note":"A community reference does not establish current availability or eligibility.",
        "application_url_verified":False,
        "verification_checked_at":datetime.now(timezone.utc).isoformat(),
    }
    try:
        response = await safe._request(client, url, headers={"User-Agent":safe.USER_AGENT, "Accept":"text/html"}, robots=True)
        parser = safe._JSONLDParser()
        parser.feed(response.text)
        for payload in parser.payloads:
            for value in safe._jsonld_jobs(payload):
                official = safe._jsonld_job(value, reference, str(response.url))
                if not official or official["title"].casefold().strip() != reference["title"].casefold().strip():
                    continue
                if safe.canonical_url(official["url"]) not in {safe.canonical_url(url), safe.canonical_url(str(response.url))}:
                    continue
                job.update(official)
                job.update(opportunity_type="internship", verification_status="official_metadata_verified",
                           application_url_verified=True,
                           verification_note="Matching JobPosting metadata was read from the linked public page under its robots policy.")
                return job
        job["verification_note"] = "The linked page responded, but matching public JobPosting metadata could not be verified."
    except safe.DiscoveryError as exc:
        # Do not expose network exception representations or query-string data.
        job["verification_note"] = "The official page could not be verified under its access or robots policy."
        if exc.retry_after:
            job["verification_retry_after"] = exc.retry_after
    except (ValueError, TypeError, KeyError, AttributeError):
        job["verification_note"] = "The linked page's public metadata was malformed; current availability remains unverified."
    return job


async def discover_opportunities(source, cache=None):
    if source.get("permitted") is not True:
        raise safe.DiscoveryError("Confirm this source permits automated read-only discovery before enabling it.")
    cache = dict(cache or {})
    kind = source.get("kind")
    if kind == "devpost":
        raise safe.DiscoveryError("No permission-verified published Devpost API is configured. Use an explicitly authorized feed; direct crawling is disabled.")
    if kind not in {"mlh", "github_list"}:
        raise safe.DiscoveryError("Unsupported opportunity connector.")
    async with httpx.AsyncClient(timeout=httpx.Timeout(30), follow_redirects=False, trust_env=True) as client:
        if kind == "mlh":
            url, season = _season_url(source)
            response = await safe._request(client, url, headers=_headers(cache, "text/html"), robots=True)
            next_cache = _cache(response, cache)
            if response.status_code == 304:
                return {"jobs":[], "cache":{**cache, **next_cache}, "not_modified":True}
            jobs = _mlh_jobs(response.text, str(response.url), season)
            return {"jobs":jobs, "cache":{**next_cache, "source_url":str(response.url), "truncated":False}, "not_modified":False}
        slug = source.get("slug") or GITHUB_REPOSITORY
        if slug.casefold() != GITHUB_REPOSITORY.casefold() or source.get("url") not in (None, "", GITHUB_ATTRIBUTION):
            raise safe.DiscoveryError("This connector supports only the attributed SimplifyJobs/Summer2027-Internships public link reference.")
        response = await safe._request(client, GITHUB_README, headers=_headers(cache, "application/vnd.github.raw+json"))
        next_cache = _cache(response, cache)
        if response.status_code == 304:
            references = cache.get("references")
            if not isinstance(references, list):
                raise safe.DiscoveryError("Cached repository references are missing; clear the source cache and retry.")
            next_cache.update(total_references=cache.get("total_references", len(references)), truncated=cache.get("truncated", False))
        else:
            all_references = _github_references(response.text)
            references = all_references[:MAX_GITHUB_LINKS]
            next_cache.update(total_references=len(all_references), truncated=len(all_references)>MAX_GITHUB_LINKS)
        semaphore = asyncio.Semaphore(3)

        async def verify(reference):
            async with semaphore:
                return await _verify_reference(client, reference)

        jobs = await asyncio.gather(*(verify(reference) for reference in references))
        # Even on README 304, recheck individual official pages. A source-cache
        # validator must not silently refresh an employer listing's verification.
        next_cache.update(references=references, source_url=GITHUB_ATTRIBUTION,
                          attribution="SimplifyJobs / Pitt CSC; minimal public link references only",
                          license_status="unverified; no code or dataset descriptions copied")
        return {"jobs":jobs, "cache":next_cache, "not_modified":False}
