import asyncio
import json

import httpx
import pytest

from app import discovery


def run(coro): return asyncio.run(coro)


@pytest.fixture
def network(monkeypatch):
    calls = []
    responses = {}
    async def request(client, url, **kwargs):
        calls.append((url, kwargs))
        body, headers, status = responses.get(url, ({}, {}, 200))
        if isinstance(body, (dict, list)): body = json.dumps(body)
        return httpx.Response(status, headers=headers, content=body, request=httpx.Request("GET", url))
    monkeypatch.setattr(discovery, "_request", request)
    return responses, calls


def test_unpermitted_and_unsupported_source_fail_closed():
    with pytest.raises(discovery.DiscoveryError, match="permits"):
        run(discovery.discover({"kind": "greenhouse", "slug": "figma"}))
    with pytest.raises(discovery.DiscoveryError, match="Unsupported"):
        run(discovery.discover({"kind": "linkedin", "permitted": True}))


def test_greenhouse_filters_deduplicates_and_does_not_invent_publication(network):
    responses, calls = network
    url = "https://boards-api.greenhouse.io/v1/boards/figma/jobs?content=true"
    responses[url] = ({"jobs": [
        {"id": 1, "title": "Software Engineer Intern", "absolute_url": "https://boards.greenhouse.io/figma/jobs/1?utm_source=test", "content": "Graduating 2029. Must be based in India. Currently pursuing a Bachelor's degree.", "updated_at": "2026-10-20T00:00:00Z"},
        {"id": 1, "title": "Software Engineer Intern", "absolute_url": "https://boards.greenhouse.io/figma/jobs/1", "content": "Graduating 2029."},
        {"id": 2, "title": "International Sales Manager", "absolute_url": "https://boards.greenhouse.io/figma/jobs/2"},
        {"id": 3, "title": "Summer Intern", "absolute_url": "http://127.0.0.1/internal"},
    ]}, {"etag": "v1"}, 200)
    result = run(discovery.discover({"kind": "greenhouse", "slug": "figma", "company": "Figma", "permitted": True}))
    assert len(result["jobs"]) == 1
    assert result["jobs"][0]["published_at"] is None
    assert result["jobs"][0]["requirements"]["graduation_years"] == [2029]
    assert result["cache"]["etag"] == "v1"


def test_conditional_caching(network):
    responses, calls = network
    url = "https://boards-api.greenhouse.io/v1/boards/figma/jobs?content=true"
    responses[url] = ("", {}, 304)
    result = run(discovery.discover({"kind": "greenhouse", "slug": "figma", "permitted": True}, {"etag": "a", "last_modified": "yesterday"}))
    assert result["not_modified"] is True
    assert result["cache"]["etag"] == "a"
    assert calls[0][1]["headers"]["If-None-Match"] == "a"


def test_lever_content_and_millisecond_dates(network):
    responses, _ = network
    url = "https://api.lever.co/v0/postings/test?mode=json"
    responses[url] = ([{"id": "1", "text": "Software Intern", "hostedUrl": "https://jobs.lever.co/test/1", "categories": {"location": "Remote"}, "descriptionPlain": "Build tools.", "lists": [{"text": "Requirements", "content": "<li>Graduating in 2029. Python required.</li>"}], "createdAt": 1700000000000}], {}, 200)
    job = run(discovery.discover({"kind": "lever", "slug": "test", "company": "Test", "permitted": True}))["jobs"][0]
    assert job["remote"] is True
    assert job["published_at"] is None
    assert job["source_created_at"].startswith("2023-11-14")
    assert "Python" in job["skills"]


def test_ashby_real_fields(network):
    responses, _ = network
    url = "https://api.ashbyhq.com/posting-api/job-board/test?includeCompensation=true"
    responses[url] = ({"jobs": [{"id": "1", "title": "AI Intern", "jobUrl": "https://jobs.ashbyhq.com/test/1", "location": "India", "descriptionHtml": "<p>Currently pursuing a Bachelor's degree, graduating 2029.</p>", "isRemote": True, "publishedAt": "2026-10-20T00:00:00Z"}]}, {}, 200)
    result = run(discovery.discover({"kind": "ashby", "slug": "test", "company": "Test", "permitted": True}))
    assert result["jobs"][0]["published_at"] == "2026-10-20T00:00:00+00:00"


def test_feed_and_robots_enforced(network):
    responses, _ = network
    source = {"kind": "feed", "url": "https://example.com/jobs.xml", "company": "Research Program", "permitted": True}
    responses["https://example.com/robots.txt"] = ("User-agent: *\nDisallow: /jobs.xml", {}, 200)
    with pytest.raises(discovery.DiscoveryError, match="robots"):
        run(discovery.discover(source))
    responses["https://example.com/robots.txt"] = ("User-agent: *\nAllow: /", {}, 200)
    responses[source["url"]] = ('<rss><channel><item><title>Research Intern</title><link>https://example.com/internship</link><description>Graduating 2029.</description><pubDate>Tue, 20 Oct 2026 00:00:00 GMT</pubDate></item></channel></rss>', {}, 200)
    result = run(discovery.discover(source))
    assert len(result["jobs"]) == 1
    assert result["jobs"][0]["published_at"].startswith("2026-10-20")


def test_public_jobposting_jsonld(network):
    responses, _ = network
    source = {"kind": "html", "url": "https://example.com/careers/1", "permitted": True}
    responses["https://example.com/robots.txt"] = ("User-agent: *\nAllow: /", {}, 200)
    payload = {"@graph": [{"@type": "JobPosting", "title": "Research Intern", "description": "Graduating in 2029", "hiringOrganization": {"name": "University"}, "datePosted": "2026-10-20", "validThrough": "2027-01-01", "jobLocationType": "TELECOMMUTE"}]}
    responses[source["url"]] = ('<script type="application/ld+json">'+json.dumps(payload)+'</script>', {}, 200)
    job = run(discovery.discover(source))["jobs"][0]
    assert job["company"] == "University" and job["remote"] is True
    assert job["deadline"].startswith("2027-01-01")


def test_hackathon_event_dates_are_not_registration_deadlines(network):
    responses,_ = network
    source = {"kind":"html","url":"https://example.com/hackathon","permitted":True,"company":"University"}
    responses["https://example.com/robots.txt"] = ("User-agent: *\nAllow: /",{},200)
    event = {"@type":"Event","name":"Student AI Hackathon","description":"Open to students worldwide. Python.",
             "eventAttendanceMode":"https://schema.org/OnlineEventAttendanceMode",
             "startDate":"2027-01-20T10:00:00+05:30","endDate":"2027-01-21T18:00:00+05:30",
             "organizer":{"name":"Synthetic University"},"location":{"@type":"VirtualLocation","url":"https://example.com"}}
    responses[source["url"]] = ('<script type="application/ld+json">'+json.dumps(event)+'</script>',{},200)
    data = run(discovery.discover(source))["jobs"][0]
    assert data["opportunity_type"] == "hackathon" and data["company"] == "Synthetic University"
    assert data["starts_at"] == "2027-01-20T04:30:00+00:00" and data["deadline"] is None
    assert data["registration_status"] == "unknown" and data["application_url_verified"] is False
    assert data["remote"] is True
    # The default JobPosting extractor used for employer verification never
    # treats an event as a verified internship.
    assert list(discovery._jsonld_jobs(event)) == []


def test_hackathon_rss_is_a_reference_and_preserves_missing_remote(network):
    responses,_ = network
    source = {"kind":"feed","url":"https://example.com/events.xml","company":"Organizer","permitted":True}
    responses["https://example.com/robots.txt"] = ("User-agent: *\nAllow: /",{},200)
    responses[source["url"]] = ('<rss><channel><item><title>Cloud Hackathon</title><link>https://example.com/hack</link><description>Python projects.</description></item><item><title>General company announcement</title><link>https://example.com/news</link></item></channel></rss>',{},200)
    jobs = run(discovery.discover(source))["jobs"]
    assert len(jobs) == 1 and jobs[0]["opportunity_type"] == "hackathon"
    assert jobs[0]["remote"] is None and jobs[0]["deadline"] is None


@pytest.mark.parametrize("url", ["http://example.com/jobs", "https://127.0.0.1/", "https://[::1]/", "https://[fd00::1]/", "https://[fe80::1]/", "https://[::ffff:10.0.0.1]/", "https://169.254.169.254/latest", "https://user:secret@example.com", "https://example.com:8080/", "https://example.local/", "https://linkedin.com/jobs", "https://www.indeed.com/jobs", "file:///etc/passwd"])
def test_unsafe_and_restricted_destinations_blocked(url):
    with pytest.raises(discovery.DiscoveryError): discovery._syntax_url(url)


def test_private_dns_record_rejected(monkeypatch):
    monkeypatch.setattr(discovery.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("10.0.0.1", 443))])
    with pytest.raises(discovery.DiscoveryError, match="Private"):
        run(discovery.validate_public_url("https://example.com/jobs"))


def test_redirect_revalidates_destination(monkeypatch):
    seen = []
    async def validate(url):
        seen.append(url)
        if "127.0.0.1" in url: raise discovery.DiscoveryError("Private destination")
        return url
    monkeypatch.setattr(discovery, "validate_public_url", validate)
    async def scenario():
        transport = httpx.MockTransport(lambda request: httpx.Response(302, headers={"location": "https://127.0.0.1/private"}))
        async with httpx.AsyncClient(transport=transport) as client:
            await discovery._request(client, "https://example.com/jobs")
    with pytest.raises(discovery.DiscoveryError, match="Private"): run(scenario())
    assert len(seen) == 2


def test_rate_limit_retry_metadata(monkeypatch):
    async def validate(url): return url
    monkeypatch.setattr(discovery, "validate_public_url", validate)
    async def scenario():
        transport = httpx.MockTransport(lambda request: httpx.Response(429, headers={"retry-after": "120"}))
        async with httpx.AsyncClient(transport=transport) as client:
            await discovery._request(client, "https://rate.example.com/jobs")
    with pytest.raises(discovery.DiscoveryError) as exc: run(scenario())
    assert exc.value.retry_after == 120


def test_search_requires_authorized_key(monkeypatch):
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    with pytest.raises(discovery.DiscoveryError, match="BRAVE_SEARCH_API_KEY"):
        run(discovery.discover({"kind": "search", "slug": "internships India", "permitted": True}))


def test_tracking_params_removed_without_losing_requisition():
    assert discovery.canonical_url("https://Example.com/job/1/?utm_source=x&gh_jid=1&source=foo#apply") == "https://example.com/job/1?gh_jid=1"


def test_compressed_api_response_is_decoded_once(monkeypatch):
    import gzip
    async def validate(url): return url
    monkeypatch.setattr(discovery, "validate_public_url", validate)
    async def scenario():
        payload = gzip.compress(b'{"jobs":[]}')
        transport = httpx.MockTransport(lambda request: httpx.Response(200, headers={"content-encoding": "gzip"}, content=payload))
        async with httpx.AsyncClient(transport=transport) as client:
            response = await discovery._request(client, "https://compressed.example.com/jobs")
            assert response.json() == {"jobs": []}
    run(scenario())


def test_smartrecruiters_details_are_cached_incrementally(network):
    responses, calls = network
    listing = "https://api.smartrecruiters.com/v1/companies/Example/postings?limit=100&offset=0"
    detail = "https://api.smartrecruiters.com/v1/companies/Example/postings/123"
    responses[listing] = ({"totalFound": 101, "content": [{"id": "123", "name": "Software Intern", "releasedDate": "2026-10-20T00:00:00Z"}]}, {}, 200)
    responses[detail] = ({"id": "123", "name": "Software Intern", "releasedDate": "2026-10-20T00:00:00Z", "location": {"city": "Bengaluru", "country": "India"}, "applyUrl": "https://jobs.smartrecruiters.com/Example/123", "jobAd": {"sections": {"qualifications": {"text": "Graduating 2029. Currently pursuing a Bachelor's degree. Must be based in India."}}}}, {}, 200)
    source = {"kind": "smartrecruiters", "slug": "Example", "company": "Example", "permitted": True}
    first = run(discovery.discover(source))
    assert first["jobs"][0]["requirements"]["graduation_years"] == [2029]
    assert first["cache"]["truncated"] is True
    calls.clear()
    second = run(discovery.discover(source, first["cache"]))
    assert second["jobs"] == first["jobs"]
    assert len(calls) == 1


def test_workday_requires_permitted_public_cxs_and_keeps_missing_details_uncertain(network):
    responses, calls = network
    url = "https://example.wd5.myworkdayjobs.com/wday/cxs/example/External/jobs"
    responses[url] = ({"total": 30, "jobPostings": [{"title": "Software Intern", "externalPath": "/job/Bengaluru/Software-Intern_123", "locationsText": "India"}]}, {}, 200)
    result = run(discovery.discover({"kind": "workday", "url": url, "company": "Example", "permitted": True}))
    assert calls[0][1]["method"] == "POST"
    assert result["jobs"][0]["url"] == "https://example.wd5.myworkdayjobs.com/External/job/Bengaluru/Software-Intern_123"
    assert result["jobs"][0]["description"] == ""
    assert result["jobs"][0]["requirements"]["uncertain"]
    assert result["cache"]["truncated"] is True
    with pytest.raises(discovery.DiscoveryError, match="CXS"):
        run(discovery.discover({"kind": "workday", "url": "https://example.com/private/jobs", "permitted": True}))


def test_cross_origin_redirect_removes_api_credentials(monkeypatch):
    headers_seen = []
    async def validate(url): return url
    monkeypatch.setattr(discovery, "validate_public_url", validate)
    def handler(request):
        headers_seen.append(dict(request.headers))
        if request.url.host == "api.example.com": return httpx.Response(302, headers={"location": "https://other.example.com/jobs"})
        return httpx.Response(200, content=b'{}')
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await discovery._request(client, "https://api.example.com/jobs", headers={"X-Subscription-Token": "test-token", "If-None-Match": "v1"})
    run(scenario())
    assert headers_seen[0]["x-subscription-token"] == "test-token"
    assert "x-subscription-token" not in headers_seen[1]


def test_retry_after_http_date_respects_full_future_delay():
    from datetime import datetime, timedelta, timezone
    from email.utils import format_datetime
    target = datetime.now(timezone.utc) + timedelta(days=2)
    delay = discovery._retry_seconds(format_datetime(target, usegmt=True))
    assert 172798 <= delay <= 172801
    assert discovery._retry_seconds("172800") == 172800
    assert discovery._retry_seconds("not a retry date") == 60
    past = datetime.now(timezone.utc) - timedelta(seconds=30)
    assert discovery._retry_seconds(format_datetime(past, usegmt=True)) == 5
