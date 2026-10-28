"""Read-only public ATS connectors and explicitly authorized feeds/search.

No login, anti-bot evasion, HTML scraping of blocked platforms, or submission APIs.
Network requests validate destinations and redirects, cap response sizes, preserve
proxy settings, use validators, and rate-limit each host. Operators must attest
permitted access before a source can run.
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
import math
import os
import re
import socket
import time
import urllib.robotparser
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import httpx

from .matching import extract_requirements, plain_text

USER_AGENT = "InternPilot/1.0 (+local-first internship discovery; public API reader)"
MAX_BYTES = 12 * 1024 * 1024
_HOST_LOCKS: dict[str, asyncio.Lock] = {}
_HOST_LAST: dict[str, float] = {}
_HOST_DELAY: dict[str, float] = {}
RESTRICTED_PLATFORMS = {"linkedin.com", "indeed.com", "wellfound.com", "internshala.com", "unstop.com"}
INTERNSHIP = re.compile(r"\bintern(?:ship)?s?\b|\bstudent\b|\bapprentic\w*\b|\bearly[- ](?:career|year)\b|\bresearch fellow(?:ship)?\b|\bundergraduate\b|\bSTEP\b|\buniversity (?:program|grad)\b", re.I)
HACKATHON = re.compile(r"\bhackathons?\b|\b(?:coding|innovation|AI|ML|cloud) (?:challenge|competition)\b",re.I)
# Small employers/university labs often omit "intern". These are discovery
# candidates, not evidence that a current undergraduate is eligible.
ADJACENT_STUDENT_ROLE = re.compile(r"\b(?:research|project) assistant\b|\b(?:software|developer|engineering|engineer|data|cloud|cybersecurity|web|graduate)[\w /&-]{0,25}\btrainee\b|\btrainee[\w /&-]{0,25}\b(?:developer|engineer|software|data)\b", re.I)
INTERNSHIP = re.compile(INTERNSHIP.pattern + "|" + ADJACENT_STUDENT_ROLE.pattern, re.I)


class DiscoveryError(ValueError):
    def __init__(self, message: str, retry_after: int | None = None):
        super().__init__(message); self.retry_after = retry_after


def default_sources() -> list[dict]:
    """Documented public read-only APIs. No preferred-employer claim is fabricated."""
    return [
        {"kind": "greenhouse", "slug": "figma", "company": "Figma", "permitted": True, "enabled": True, "interval_seconds": 900},
        {"kind": "lever", "slug": "palantir", "company": "Palantir", "permitted": True, "enabled": True, "interval_seconds": 1800},
        {"kind": "ashby", "slug": "ramp", "company": "Ramp", "permitted": True, "enabled": True, "interval_seconds": 900},
        {"kind": "mlh", "slug": "", "company": "Major League Hacking", "permitted": True, "enabled": True, "interval_seconds": 1800},
        {"kind": "internscan", "slug": "india", "company": "InternScan India feed", "url":"https://internscan.vercel.app/in/api/active.json", "permitted": True, "enabled": True, "interval_seconds": 900},
        {"kind": "ashby", "slug": "sarvam", "company": "Sarvam AI", "permitted": True, "enabled": True, "interval_seconds": 1800},
    ]


def canonical_url(url: str) -> str:
    parsed = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in {"source", "ref", "referrer", "lever-source", "gh_src"}]
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/") or "/", urlencode(sorted(query)), ""))


def _syntax_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
            raise ValueError
        host = parsed.hostname.rstrip(".").lower()
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            raise ValueError
        try:
            if not ipaddress.ip_address(host).is_global: raise ValueError
        except ValueError:
            if re.fullmatch(r"[\d.:]+", host): raise ValueError
        if any(host == blocked or host.endswith("." + blocked) for blocked in RESTRICTED_PLATFORMS):
            raise DiscoveryError("This platform requires an authorized API/feed integration; direct page crawling is disabled.")
        return url
    except (ValueError, TypeError):
        raise DiscoveryError("Discovery requires an HTTPS public destination without credentials or custom ports.") from None


async def validate_public_url(url: str) -> str:
    _syntax_url(url)
    host = urlsplit(url).hostname
    try:
        records = await asyncio.to_thread(socket.getaddrinfo, host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise DiscoveryError("The source hostname could not be resolved.") from exc
    if not records or any(not ipaddress.ip_address(record[4][0]).is_global for record in records):
        raise DiscoveryError("Private, loopback, link-local, or reserved destinations are forbidden.")
    return url


def _retry_seconds(value: str | None) -> int:
    """Return the full server delay; scheduling must not retry before Retry-After.

    HTTP allows either integer seconds or an RFC HTTP-date. This value is handed
    to the durable scheduler; request throttling separately limits inline waits.
    """
    if not value:
        return 60
    try:
        return max(5, int(value.strip()))
    except (ValueError, TypeError):
        from email.utils import parsedate_to_datetime
        try:
            target = parsedate_to_datetime(value)
            if target.tzinfo is None:
                target = target.replace(tzinfo=timezone.utc)
            return max(5, math.ceil((target - datetime.now(timezone.utc)).total_seconds()))
        except (ValueError, TypeError, OverflowError):
            return 60


async def _request(client: httpx.AsyncClient, url: str, *, headers=None, method="GET", payload=None, robots=False) -> httpx.Response:
    for _ in range(6):
        await validate_public_url(url)
        if robots:
            await _robots(client, url)
        host = urlsplit(url).hostname
        lock = _HOST_LOCKS.setdefault(host, asyncio.Lock())
        async with lock:
            delay = _HOST_DELAY.get(host, 1.0)
            remaining = delay - (time.monotonic() - _HOST_LAST.get(host, 0))
            if remaining > 0: await asyncio.sleep(min(remaining, 60))
            _HOST_LAST[host] = time.monotonic()
            from .rate_limits import throttle
            await throttle(host,delay)
            try:
                async with client.stream(method, url, headers=headers, json=payload if method == "POST" else None) as response:
                    chunks, size = [], 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > MAX_BYTES: raise DiscoveryError("Source response exceeds the 12 MiB safety limit.")
                        chunks.append(chunk)
                    # aiter_bytes already decoded compression; do not decode again.
                    decoded_headers = {k: v for k, v in response.headers.items() if k.lower() not in {"content-encoding", "transfer-encoding", "content-length"}}
                    result = httpx.Response(response.status_code, headers=decoded_headers, content=b"".join(chunks), request=response.request)
            except httpx.HTTPError as exc:
                raise DiscoveryError(f"Source request failed ({type(exc).__name__}); no access restriction was bypassed.") from exc
        if result.status_code in (301, 302, 303, 307, 308):
            target = result.headers.get("location")
            if not target: raise DiscoveryError("Source returned an invalid redirect.")
            new_url = urljoin(url, target)
            # Never forward API credentials across origins.
            if urlsplit(new_url).netloc != urlsplit(url).netloc:
                headers = {k: v for k, v in (headers or {}).items() if k.lower() not in {"authorization", "x-subscription-token", "x-api-key"}}
            url = new_url
            if result.status_code == 303: method, payload = "GET", None
            continue
        if result.status_code == 429:
            retry = _retry_seconds(result.headers.get("retry-after"))
            from .rate_limits import cooldown
            await cooldown(host,retry)
            _HOST_DELAY[host] = max(_HOST_DELAY.get(host, 1), min(retry, 60))
            raise DiscoveryError("Source rate limit reached; retry after the server's requested delay.", retry_after=retry)
        if result.status_code in (401, 403):
            raise DiscoveryError("Source requires authorization or disallows access; configure an authorized feed instead.")
        if result.status_code == 304: return result
        if result.is_error: raise DiscoveryError(f"Source returned HTTP {result.status_code}.")
        return result
    raise DiscoveryError("Source exceeded the redirect limit.")


def _iso(value):
    if not value: return None
    if isinstance(value, (float, int)):
        try: return datetime.fromtimestamp(value/1000 if value > 10**11 else value, timezone.utc).isoformat()
        except (ValueError, OSError): return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return (dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)).isoformat()
    except ValueError:
        from email.utils import parsedate_to_datetime
        try: return parsedate_to_datetime(str(value)).isoformat()
        except (ValueError, TypeError): return None


def _job(*, external_id, title, company, location="", url, description="", remote=False,
         published_at=None, deadline=None, compensation=None, source_created_at=None):
    if not INTERNSHIP.search(str(title)): return None
    try: _syntax_url(url)
    except DiscoveryError: return None
    text = plain_text(description)
    req = extract_requirements(text, location=location, title=title)
    adjacent = bool(ADJACENT_STUDENT_ROLE.search(str(title)) and not re.search(r"\bintern(?:ship)?s?\b", str(title), re.I))
    if adjacent:
        req["uncertain"].append("An adjacent trainee/assistant title does not confirm current-student eligibility; review the publisher's requirements.")
    return {"external_id": str(external_id), "title": str(title).strip(), "company": str(company),
            "location": location or "Not specified", "remote": bool(remote), "url": canonical_url(url),
            "description": text[:100000], "skills": req["skills"], "requirements": req,
            "published_at": _iso(published_at), "source_created_at": _iso(source_created_at), "deadline": _iso(deadline), "compensation": compensation,
            "adjacent_student_role": adjacent}


def _slug(source):
    slug = source.get("slug", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", slug):
        raise DiscoveryError("Use a valid public ATS board slug (letters, numbers, hyphens, underscores).")
    return slug


async def _robots(client, url):
    parsed = urlsplit(url)
    robots_url = urlunsplit((parsed.scheme, parsed.netloc, "/robots.txt", "", ""))
    try: response = await _request(client, robots_url)
    except DiscoveryError as exc:
        if "HTTP 404" in str(exc): return
        raise DiscoveryError("Cannot verify robots permission for this source; use an authorized API or feed.", retry_after=exc.retry_after) from exc
    parser = urllib.robotparser.RobotFileParser(); parser.parse(response.text.splitlines())
    if not parser.can_fetch(USER_AGENT, url): raise DiscoveryError("The source robots.txt disallows discovery.")
    delay = parser.crawl_delay(USER_AGENT) or parser.crawl_delay("*")
    if delay:
        if delay > 60: raise DiscoveryError("The source requires a crawl delay above this connector's limit; use an authorized feed.")
        _HOST_DELAY[parsed.hostname] = max(1, float(delay))


class _JSONLDParser(HTMLParser):
    def __init__(self): super().__init__(); self.active = False; self.parts = []; self.payloads = []
    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("type", "").lower() == "application/ld+json": self.active = True; self.parts = []
    def handle_data(self, data):
        if self.active: self.parts.append(data)
    def handle_endtag(self, tag):
        if tag == "script" and self.active:
            try: self.payloads.append(json.loads("".join(self.parts)))
            except (json.JSONDecodeError, ValueError): pass
            self.active = False


def _jsonld_jobs(payload, types=("JobPosting",)):
    if isinstance(payload, list):
        for value in payload: yield from _jsonld_jobs(value,types)
    elif isinstance(payload, dict):
        typ = payload.get("@type", "")
        if isinstance(typ,str) and typ in types or isinstance(typ,list) and any(t in types for t in typ): yield payload
        if "@graph" in payload: yield from _jsonld_jobs(payload["@graph"],types)


def _event(value, source, base_url):
    title = value.get("name","")
    if not isinstance(title,str) or not HACKATHON.search(title):
        return None
    url = urljoin(base_url,value.get("url") or base_url)
    try: _syntax_url(url)
    except DiscoveryError: return None
    organizer = value.get("organizer") or {}
    if isinstance(organizer,list): organizer = organizer[0] if organizer else {}
    company = organizer.get("name") if isinstance(organizer,dict) else organizer
    location = value.get("location") or {}
    if isinstance(location,list): location = location[0] if location else {}
    address = location.get("address") if isinstance(location,dict) else None
    if isinstance(address,dict): address = ", ".join(str(address[k]) for k in ("addressLocality","addressRegion","addressCountry") if address.get(k))
    description = plain_text(str(value.get("description") or ""))[:100000]
    mode = value.get("eventAttendanceMode","")
    remote = True if str(mode).endswith("OnlineEventAttendanceMode") else False if str(mode).endswith("OfflineEventAttendanceMode") else None
    def aware(value):
        try:
            dt = datetime.fromisoformat(str(value).replace("Z","+00:00"))
            return dt.astimezone(timezone.utc).isoformat() if dt.tzinfo else None
        except (ValueError,TypeError): return None
    return {"external_id":str(value.get("@id") or url),"opportunity_type":"hackathon","title":title,
            "company":str(company or source.get("company") or "Event organizer"),"url":canonical_url(url),
            "location":str(address or (location.get("name") if isinstance(location,dict) else location) or "Not specified"),
            "description":description,"skills":extract_requirements(description)["skills"],"requirements":{},"remote":remote,
            "starts_at":aware(value.get("startDate")),"ends_at":aware(value.get("endDate")),
            "published_at":aware(value.get("datePublished")),"deadline":None,"compensation":None,
            "active":not str(value.get("eventStatus","")).endswith("EventCancelled"),
            "registration_status":"unknown","application_url_verified":False,
            "verification_note":"Publisher announcement. Verify registration availability and eligibility on the event website."}


def _jsonld_job(value, source, base_url):
    company = value.get("hiringOrganization") or {}
    locations = value.get("jobLocation") or []
    if not isinstance(locations, list): locations = [locations]
    texts = []
    for loc in locations:
        if not isinstance(loc, dict): continue
        address = loc.get("address") or {}
        if isinstance(address, str): texts.append(address)
        elif isinstance(address, dict): texts.append(", ".join(str(address.get(k)) for k in ("addressLocality", "addressRegion", "addressCountry") if address.get(k)))
    compensation = value.get("baseSalary")
    if compensation: compensation = json.dumps(compensation, ensure_ascii=False)[:800]
    ident = value.get("identifier") or value.get("url") or value.get("title")
    if isinstance(ident, dict): ident = ident.get("value", ident.get("name", value.get("title")))
    return _job(external_id=ident, title=value.get("title", ""), company=company.get("name", source.get("company", "")) if isinstance(company, dict) else str(company),
                location=", ".join(texts), url=urljoin(base_url, value.get("url") or base_url), description=value.get("description", ""),
                remote=value.get("jobLocationType") == "TELECOMMUTE", published_at=value.get("datePosted"), deadline=value.get("validThrough"), compensation=compensation)


def _feed_jobs(text, source, base_url):
    try: root = ET.fromstring(text)
    except ET.ParseError as exc: raise DiscoveryError("The source is not a valid RSS/Atom feed.") from exc
    jobs = []
    for item in root.iter():
        if item.tag.split("}")[-1] not in {"item", "entry"}: continue
        fields = {}
        for child in item:
            name = child.tag.split("}")[-1]
            fields[name] = "".join(child.itertext()).strip()
            if name == "link" and child.get("href"): fields[name] = child.get("href")
        title = fields.get("title", "")
        if HACKATHON.search(title):
            event = _event({"name":title,"url":fields.get("link"),"description":fields.get("description") or fields.get("content") or fields.get("summary","")},source,base_url)
            if event:
                event["published_at"] = _iso(fields.get("pubDate") or fields.get("published") or fields.get("updated"))
                jobs.append(event)
            continue
        job = _job(external_id=fields.get("guid") or fields.get("id") or fields.get("link") or title,
                   title=title, company=source.get("company", "Feed announcement"),
                   url=urljoin(base_url, fields.get("link", "")), description=fields.get("description") or fields.get("content") or fields.get("summary", ""),
                   published_at=fields.get("pubDate") or fields.get("published") or fields.get("updated"))
        if job: jobs.append(job)
    return jobs


async def _search_reference(client, value: dict, source: dict, *, verify: bool, candidates=None) -> dict | None:
    """Search snippets are references; only matching publisher metadata supplies location."""
    title, url = str(value.get("title") or ""), str(value.get("url") or "")
    try:
        _syntax_url(url)
    except DiscoveryError:
        return None
    kind = "hackathon" if HACKATHON.search(title) else "internship" if INTERNSHIP.search(title) else None
    if kind is None:
        return None
    job = {"external_id":url,"opportunity_type":kind,"title":title,"url":canonical_url(url),
           "company":"Search reference — employer unverified","location":"Not specified","remote":False,
           "description":"","search_snippet":plain_text(str(value.get("description") or ""))[:2000],"skills":[],"requirements":{},
           "published_at":None,"deadline":None,"compensation":None,"source":source.get("kind", "search"),
           "discovery_query":source.get("slug"),"verification_status":"reference_only","application_url_verified":False,
           "verification_note":"Search reference. Location, eligibility, deadline and current application availability have not been verified."}
    if kind == "hackathon":
        job["registration_status"] = "unknown"
    if not verify:
        return job
    try:
        response = await _request(client,url,headers={"User-Agent":USER_AGENT,"Accept":"text/html"},robots=True)
        if candidates is not None:
            from .publisher_discovery import page_candidates
            candidates.extend(page_candidates(response.text, str(response.url)))
        parser = _JSONLDParser()
        parser.feed(response.text)
        accepted = {canonical_url(url),canonical_url(str(response.url))}
        for payload in parser.payloads:
            for item in _jsonld_jobs(payload,("JobPosting",) if kind=="internship" else ("Event","Hackathon")):
                official = _jsonld_job(item,{},str(response.url)) if kind=="internship" else _event(item,{},str(response.url))
                if official and canonical_url(official["url"]) in accepted:
                    job.update(official)
                    job.update(verification_status="official_metadata_verified",source=source.get("kind", "search"),verification_evidence_url=canonical_url(str(response.url)),
                               verification_note="Matching structured metadata was read from the linked publisher under its robots policy. Eligibility still requires review.")
                    if kind=="internship":
                        job["application_url_verified"] = True
                    return job
    except (DiscoveryError,ValueError,TypeError,KeyError,AttributeError):
        job["verification_note"] = "Publisher metadata could not be verified under its access policy or supported schema. Review the reference manually."
    return job


async def discover(source: dict, cache: dict | None = None) -> dict:
    if source.get("permitted") is not True:
        raise DiscoveryError("Confirm that this source permits automated read-only discovery before enabling it.")
    if source.get("kind") in {"mlh", "github_list", "devpost"}:
        from .opportunity_sources import discover_opportunities
        return await discover_opportunities(source, cache)
    if source.get("kind") in {"internscan", "jobspy_feed"}:
        from .aggregation import discover_aggregation
        return await discover_aggregation(source, cache)
    cache = dict(cache or {})
    kind, company = source.get("kind"), source.get("company", "")
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if cache.get("etag"): headers["If-None-Match"] = cache["etag"]
    if cache.get("last_modified"): headers["If-Modified-Since"] = cache["last_modified"]
    if kind == "greenhouse": url = f"https://boards-api.greenhouse.io/v1/boards/{_slug(source)}/jobs?content=true"
    elif kind == "lever": url = f"https://api.lever.co/v0/postings/{_slug(source)}?mode=json"
    elif kind == "ashby": url = f"https://api.ashbyhq.com/posting-api/job-board/{_slug(source)}?includeCompensation=true"
    elif kind == "smartrecruiters": url = f"https://api.smartrecruiters.com/v1/companies/{_slug(source)}/postings?limit=100&offset=0"
    elif kind in {"feed", "html"}:
        url = source.get("url", ""); _syntax_url(url); headers["Accept"] = "application/xml,text/html,application/json"
    elif kind == "workday":
        url = source.get("url", "")
        if not re.fullmatch(r"https://[A-Za-z0-9.-]+\.myworkdayjobs\.com/wday/cxs/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+/jobs", url):
            raise DiscoveryError("Workday requires an explicitly permitted public CXS jobs endpoint. Authentication or restricted boards are unsupported.")
    elif kind == "search":
        token = os.environ.get("BRAVE_SEARCH_API_KEY")
        if not token: raise DiscoveryError("Authorized search requires BRAVE_SEARCH_API_KEY; no search integration is configured.")
        query = source.get("slug") or source.get("query") or "undergraduate software internship India"
        from .regional_search import search_freshness
        parameters = {"q": query, "count": 20}
        freshness = search_freshness(source)
        if freshness:
            parameters["freshness"] = freshness
        url = "https://api.search.brave.com/res/v1/web/search?" + urlencode(parameters)
        headers["X-Subscription-Token"] = token
    else: raise DiscoveryError("Unsupported connector. Use a documented public ATS API, authorized feed, or permitted JobPosting page.")
    jobs, source_candidates = [], []
    async with httpx.AsyncClient(timeout=httpx.Timeout(30), follow_redirects=False, trust_env=True) as client:
        if kind in {"html", "feed"}: await _robots(client, url)
        if kind == "workday":
            response = await _request(client, url, headers=headers, method="POST", payload={"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": "intern"})
        else: response = await _request(client, url, headers=headers)
        next_cache = {"etag": response.headers.get("etag"), "last_modified": response.headers.get("last-modified"), "checked_at": datetime.now(timezone.utc).isoformat()}
        if response.status_code == 304:
            return {"jobs": [], "cache": {**cache, "checked_at": next_cache["checked_at"]}, "not_modified": True}
        if kind == "html":
            from .publisher_discovery import page_candidates, page_links
            source_candidates.extend(page_candidates(response.text, str(response.url)))
            parser = _JSONLDParser(); parser.feed(response.text)
            for payload in parser.payloads:
                jobs.extend(_jsonld_job(value,source,str(response.url)) for value in _jsonld_jobs(payload))
                jobs.extend(_event(value,source,str(response.url)) for value in _jsonld_jobs(payload,("Event","Hackathon")))
            for job in jobs:
                if job:
                    job["verification_evidence_url"] = canonical_url(str(response.url))
            next_cache["publisher_url"] = canonical_url(str(response.url))
            # A small employer may expose ordinary links rather than JSON-LD.
            # Follow at most three same-origin opportunity links under robots;
            # plain links remain explicitly unverified, with no inferred facts.
            structured_urls = {job["url"] for job in jobs if job}
            links = [link for link in page_links(response.text, str(response.url))
                     if (INTERNSHIP.search(link["title"]) or HACKATHON.search(link["title"]))
                     and urlsplit(link["url"]).netloc == urlsplit(str(response.url)).netloc
                     and canonical_url(link["url"]) not in structured_urls][:20]
            for index, link in enumerate(links):
                jobs.append(await _search_reference(client, link, source, verify=index < 3, candidates=source_candidates))
            next_cache["truncated"] = True  # One publisher page never proves a complete inventory.
            if not parser.payloads and not links and not source_candidates:
                raise DiscoveryError("No supported opportunity metadata or career/feed links were found. PDF-only or script-rendered announcements require manual review or an authorized feed.")
        elif kind == "feed": jobs = _feed_jobs(response.text, source, str(response.url))
        else:
            try: data = response.json()
            except ValueError as exc: raise DiscoveryError("The source did not return valid API JSON.") from exc
            if kind == "greenhouse":
                for value in data.get("jobs", []):
                    location = (value.get("location") or {}).get("name", "")
                    jobs.append(_job(external_id=value["id"], title=value.get("title", ""), company=company, location=location,
                                     url=value.get("absolute_url", ""), description=value.get("content", ""), remote="remote" in location.lower(),
                                     # Greenhouse updated_at is not an original publication date.
                                     published_at=value.get("first_published"), compensation=None))
            elif kind == "lever":
                if not isinstance(data, list): raise DiscoveryError("Unexpected Lever response schema.")
                for value in data:
                    categories = value.get("categories") or {}; location = categories.get("location", "")
                    sections = "\n".join(plain_text(v.get("text", "") + " " + v.get("content", "")) for v in value.get("lists", []))
                    salary = value.get("salaryRange")
                    compensation = f"{salary.get('currency', '')} {salary.get('min', '')}–{salary.get('max', '')} {salary.get('interval', '')}" if salary else None
                    jobs.append(_job(external_id=value["id"], title=value.get("text", ""), company=company, location=location,
                                     url=value.get("hostedUrl", ""), description=(value.get("descriptionPlain") or plain_text(value.get("description", ""))) + "\n" + sections + "\n" + plain_text(value.get("additional", "")),
                                     remote=value.get("workplaceType") == "remote" or "remote" in location.lower(), published_at=value.get("publishedAt"), source_created_at=value.get("createdAt"), compensation=compensation))
            elif kind == "ashby":
                for value in data.get("jobs", []):
                    compensation = value.get("compensation")
                    jobs.append(_job(external_id=value.get("id") or value.get("jobUrl"), title=value.get("title", ""), company=company, location=value.get("location", ""),
                                     url=value.get("jobUrl", ""), description=value.get("descriptionPlain") or value.get("descriptionHtml", ""),
                                     remote=value.get("isRemote") is True, published_at=value.get("publishedAt"),
                                     compensation=json.dumps(compensation, ensure_ascii=False)[:1200] if compensation else None))
            elif kind == "smartrecruiters":
                details_cache = cache.get("details") or {}; new_details = {}
                postings = data.get("content", [])
                # Fetch only changed relevant details; limit work per run and cache it.
                for value in postings:
                    if not INTERNSHIP.search(value.get("name", "")): continue
                    ident = str(value["id"]); released = value.get("releasedDate")
                    detail = details_cache.get(ident, {})
                    if not detail or detail.get("releasedDate") != released:
                        detail_response = await _request(client, f"https://api.smartrecruiters.com/v1/companies/{_slug(source)}/postings/{ident}", headers={"User-Agent": USER_AGENT})
                        detail = detail_response.json()
                    new_details[ident] = detail
                    loc = detail.get("location") or value.get("location") or {}
                    sections = ((detail.get("jobAd") or {}).get("sections") or {}).values()
                    description = "\n".join(section.get("text", "") for section in sections)
                    jobs.append(_job(external_id=ident, title=value.get("name", ""), company=company,
                                     location=", ".join(str(loc.get(k)) for k in ("city", "region", "country") if loc.get(k)),
                                     url=detail.get("applyUrl") or f"https://jobs.smartrecruiters.com/{_slug(source)}/{ident}",
                                     description=description, remote=loc.get("remote") is True, published_at=released))
                    if len(new_details) >= 20: break
                next_cache["details"] = new_details
                next_cache["truncated"] = data.get("totalFound", 0) > 100
            elif kind == "workday":
                # Public listing metadata is enough for discovery; detail eligibility remains review.
                board_base = url.split("/wday/cxs/")[0]
                board = url.split("/wday/cxs/")[1].split("/")[1]
                for value in data.get("jobPostings", []):
                    path = value.get("externalPath", "")
                    jobs.append(_job(external_id=path, title=value.get("title", ""), company=company,
                                     location=value.get("locationsText", ""), url=board_base + "/" + board + "/" + path.lstrip("/"), description="",
                                     remote="remote" in value.get("locationsText", "").lower()))
                next_cache["truncated"] = data.get("total", 0) > 20
            elif kind == "search":
                from .publisher_discovery import page_candidates, source_candidate
                results = [value for value in (data.get("web") or {}).get("results", []) if isinstance(value,dict)][:20]
                candidates = [value for value in results if INTERNSHIP.search(str(value.get("title") or "")) or HACKATHON.search(str(value.get("title") or ""))]
                for index, value in enumerate(candidates):
                    jobs.append(await _search_reference(client,value,source,verify=index<3,candidates=source_candidates))
                for value in results:
                    candidate = source_candidate(str(value.get("url") or ""), str(value.get("title") or ""), str(value.get("url") or ""))
                    if candidate:
                        source_candidates.append(candidate)
                # Employer/incubator search results need not mention internships
                # in their title. Spend only the remaining publisher-read budget
                # finding their actual ATS/careers/feed links, never invented jobs.
                reads_left = max(0, 3 - len(candidates))
                for value in [item for item in results if item not in candidates][:reads_left]:
                    try:
                        page = await _request(client, str(value.get("url") or ""), headers={"User-Agent":USER_AGENT,"Accept":"text/html"}, robots=True)
                        source_candidates.extend(page_candidates(page.text, str(page.url)))
                    except (DiscoveryError, ValueError, TypeError):
                        continue
                next_cache["truncated"] = True  # Search results never establish a complete employer inventory.
    if kind in {"search", "html"}:
        from .publisher_discovery import merge_candidates
        next_cache["source_candidates"] = merge_candidates(cache.get("source_candidates", []), source_candidates)
    dedup = {}
    for job in jobs:
        if job: dedup[job["url"]] = job
    return {"jobs": list(dedup.values()), "cache": next_cache, "not_modified": False}
