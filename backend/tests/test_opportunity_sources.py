"""Publisher-metadata parsing and fail-closed access checks, without live requests."""
import asyncio
import json

import httpx
import pytest

from app import discovery, opportunity_sources as sources


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def network(monkeypatch):
    responses, calls = {}, []

    async def request(client, url, **kwargs):
        calls.append((url, kwargs))
        value = responses[url]
        if isinstance(value, Exception):
            raise value
        body, headers, status = value
        return httpx.Response(status, headers=headers, text=body, request=httpx.Request("GET", url))

    monkeypatch.setattr(discovery, "_request", request)
    return responses, calls


def calendar(events):
    return '<script data-page="app" type="application/json">' + json.dumps({"props":{"upcomingEvents":events}}) + '</script>'


def event(**overrides):
    return {"id":"event-id", "name":"Real University Hackathon", "status":"pending",
            "url":"/events/university-hackathon/prizes", "websiteUrl":"https://university.example/hackathon",
            "startsAt":"2027-02-01T09:00:00Z", "endsAt":"2027-02-02T17:00:00Z",
            "formatType":"physical", "location":"Bengaluru, India", "venueAddress":{"country":"IN"}, **overrides}


def table(rows):
    return '<table><tbody>' + ''.join(
        f'<tr><td>{company}</td><td>{title}</td><td>Location must not be imported from the community dataset</td><td>{links}</td><td>1d</td></tr>'
        for company, title, links in rows) + '</tbody></table>'


def reference_page(url="https://jobs.example.com/1", title="Software Engineer Intern", company="Verified Employer"):
    return '<script type="application/ld+json">' + json.dumps({"@type":"JobPosting", "title":title,
            "hiringOrganization":{"name":company}, "url":url, "description":"Official publisher description. Graduating 2029.",
            "jobLocation":{"address":{"addressCountry":"India"}}, "datePosted":"2026-10-20"}) + '</script>'


def test_mlh_reads_only_official_upcoming_events_and_keeps_unknown_deadlines(network):
    responses, calls = network
    url = "https://www.mlh.com/seasons/2027/events"
    responses[url] = (calendar([event(), event(id="canceled", status="canceled"), event(id="private", url="https://127.0.0.1/private")]), {"etag":"season-v1"}, 200)
    result = run(sources.discover_opportunities({"kind":"mlh", "slug":"2027", "permitted":True}))
    assert len(result["jobs"]) == 1
    job = result["jobs"][0]
    assert job["opportunity_type"] == "hackathon"
    assert job["starts_at"] == "2027-02-01T09:00:00+00:00"
    assert job["deadline"] is None and job["published_at"] is None and job["compensation"] is None
    assert job["verification_status"] == "source_verified"
    assert job["registration_status"] == "unknown" and job["application_url_verified"] is False
    assert job["requirements"]["uncertain"]
    assert job["official_url"] == "https://university.example/hackathon"
    assert calls == [(url, {"headers":{"User-Agent":discovery.USER_AGENT, "Accept":"text/html"}, "robots":True})]


def test_mlh_conditional_response_preserves_cached_validator(network):
    responses, calls = network
    url = "https://www.mlh.com/seasons/2027/events"
    responses[url] = ("", {}, 304)
    result = run(sources.discover_opportunities({"kind":"mlh", "url":"https://mlh.io/seasons/2027/events", "permitted":True}, {"etag":"v1"}))
    assert result["not_modified"] is True
    assert result["cache"]["etag"] == "v1"
    assert calls[0][1]["headers"]["If-None-Match"] == "v1"


@pytest.mark.parametrize("url", ["https://fake-mlh.com/seasons/2027/events", "http://mlh.io/seasons/2027/events",
                                 "https://mlh.io/admin", "https://user:pass@mlh.io/seasons/2027/events"])
def test_mlh_rejects_unofficial_or_unsafe_source_configuration(network, url):
    with pytest.raises(discovery.DiscoveryError, match="official HTTPS"):
        run(sources.discover_opportunities({"kind":"mlh", "url":url, "permitted":True}))
    assert network[1] == []


def test_mlh_schema_change_and_robots_denial_fail_without_fake_results(network):
    responses, _ = network
    url = "https://www.mlh.com/seasons/2027/events"
    responses[url] = ("<html>Login needed</html>", {}, 200)
    with pytest.raises(discovery.DiscoveryError, match="schema"):
        run(sources.discover_opportunities({"kind":"mlh", "slug":"2027", "permitted":True}))
    responses[url] = discovery.DiscoveryError("robots disallows access")
    with pytest.raises(discovery.DiscoveryError, match="robots"):
        run(sources.discover_opportunities({"kind":"mlh", "slug":"2027", "permitted":True}))


def test_repository_retains_only_attributed_links_and_independently_verified_facts(network):
    responses, calls = network
    url = "https://jobs.example.com/1"
    responses[sources.GITHUB_README] = (table([("Verified Employer", "Software Engineer Intern", f'<a href="{url}?utm_source=list">Apply</a><a href="https://simplify.jobs/p/ref">Simplify</a>')]), {"etag":"readme-v1"}, 200)
    responses[url] = (reference_page(), {}, 200)
    result = run(sources.discover_opportunities({"kind":"github_list", "permitted":True}))
    job = result["jobs"][0]
    assert job["url"] == url
    assert job["opportunity_type"] == "internship"
    assert job["verification_status"] == "official_metadata_verified"
    assert job["application_url_verified"] is True
    assert job["description"].startswith("Official publisher description")
    assert job["location"] == "India"
    assert "Community" not in job["description"]
    assert "SimplifyJobs" in job["attribution"]
    assert job["verification_checked_at"]
    assert result["cache"]["references"] == [{"company":"Verified Employer", "title":"Software Engineer Intern", "url":url}]
    assert "descriptions" in result["cache"]["license_status"]
    assert calls[1][1]["robots"] is True


def test_repository_missing_or_blocked_official_metadata_stays_unverified(network):
    responses, calls = network
    links = ["https://jobs.example.com/login", "https://blocked.example.com/2"]
    responses[sources.GITHUB_README] = (table([("Employer", "Software Intern", f'<a href="{url}">Apply</a>') for url in links]), {}, 200)
    responses[links[0]] = ("<html>Sign in. Position no longer exists.</html>", {}, 200)
    responses[links[1]] = discovery.DiscoveryError("robots forbids this page")
    jobs = run(sources.discover_opportunities({"kind":"github_list", "permitted":True}))["jobs"]
    assert len(jobs) == 2
    assert all(job["verification_status"] == "unverified" and job["description"] == "" for job in jobs)
    assert all(job["application_url_verified"] is False for job in jobs)
    assert all(job["requirements"]["uncertain"] for job in jobs)
    assert all(kwargs.get("robots") is True for url, kwargs in calls if url in links)


def test_repository_cache_rechecks_official_page_even_when_readme_unchanged(network):
    responses, calls = network
    url = "https://jobs.example.com/1"
    responses[sources.GITHUB_README] = ("", {}, 304)
    responses[url] = discovery.DiscoveryError("Source returned HTTP 404")
    cache = {"etag":"v1", "references":[{"company":"Employer", "title":"Software Intern", "url":url}], "truncated":True, "total_references":100}
    result = run(sources.discover_opportunities({"kind":"github_list", "permitted":True}, cache))
    assert result["not_modified"] is False
    assert result["jobs"][0]["verification_status"] == "unverified"
    assert len(calls) == 2
    assert result["cache"]["truncated"] is True


def test_repository_link_parser_handles_continuations_and_rejects_unsafe_or_aggregator_links():
    rows = [("<strong>Employer</strong>", "Software Intern", '<a href="https://jobs.example.com/1?ref=source">Apply</a>'),
            ("↳", "AI Intern", '<a href="https://jobs.example.com/2">Apply</a>'),
            ("Employer", "Data Intern", '<a href="https://simplify.jobs/p/only">Apply</a>'),
            ("Employer", "Research Intern", '<a href="https://127.0.0.1/private">Apply</a>')]
    assert sources._github_references(table(rows)) == [
        {"company":"Employer", "title":"Software Intern", "url":"https://jobs.example.com/1"},
        {"company":"Employer", "title":"AI Intern", "url":"https://jobs.example.com/2"}]
    markdown = '| [Employer](https://example.com) | Summer Intern | Location | [Apply](https://jobs.example.com/3) | 1d |'
    assert sources._github_references(markdown)[0]["url"] == "https://jobs.example.com/3"


def test_repository_verification_work_is_bounded_and_marked_partial(network, monkeypatch):
    responses, calls = network
    monkeypatch.setattr(sources, "MAX_GITHUB_LINKS", 2)
    urls = [f"https://jobs.example.com/{index}" for index in range(4)]
    responses[sources.GITHUB_README] = (table([("Employer", "Software Intern", f'<a href="{url}">Apply</a>') for url in urls]), {}, 200)
    for url in urls:
        responses[url] = ("No public metadata", {}, 200)
    result = run(sources.discover_opportunities({"kind":"github_list", "permitted":True}))
    assert len(result["jobs"]) == 2
    assert result["cache"]["truncated"] is True
    assert result["cache"]["total_references"] == 4
    assert len(calls) == 3


def test_devpost_is_explicitly_unsupported_without_verified_api_permission(network):
    with pytest.raises(discovery.DiscoveryError, match="permission-verified published Devpost API"):
        run(sources.discover_opportunities({"kind":"devpost", "permitted":True}))
    assert network[1] == []


def test_connector_requires_permission_and_known_repository_before_any_network(network):
    with pytest.raises(discovery.DiscoveryError, match="permits"):
        run(sources.discover_opportunities({"kind":"mlh"}))
    with pytest.raises(discovery.DiscoveryError, match="only the attributed"):
        run(sources.discover_opportunities({"kind":"github_list", "slug":"unknown/repo", "permitted":True}))
    assert network[1] == []
