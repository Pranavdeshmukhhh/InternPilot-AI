"""Small-employer discovery uses real links; fixtures never grant permission."""
import asyncio
import json
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from app import discovery
from app.matching import evaluate
from app.publisher_discovery import merge_candidates, page_candidates, page_links, source_candidate
from app.schemas import Profile
from app.services import merge_opportunity_data
from test_api_worker import stack  # noqa: F401,F811 -- isolated real API fixture


@pytest.mark.parametrize("url,kind,slug", [
    ("https://boards.greenhouse.io/tinyteam/jobs/123", "greenhouse", "tinyteam"),
    ("https://job-boards.greenhouse.io/tinyteam", "greenhouse", "tinyteam"),
    ("https://boards-api.greenhouse.io/v1/boards/tinyteam/jobs", "greenhouse", "tinyteam"),
    ("https://jobs.lever.co/tinyteam/123", "lever", "tinyteam"),
    ("https://jobs.ashbyhq.com/tinyteam/123", "ashby", "tinyteam"),
    ("https://careers.smartrecruiters.com/TinyTeam", "smartrecruiters", "TinyTeam"),
    ("https://small.example/careers", "html", ""),
    ("https://college.example/research/internships", "html", ""),
    ("https://small.example/updates.xml", "feed", ""),
])
def test_actual_links_become_unverified_source_proposals(url, kind, slug):
    candidate = source_candidate(url, "Publisher career link", "https://directory.example/portfolio")
    assert candidate["kind"] == kind and candidate["slug"] == slug
    assert candidate["verified"] is False and "permitted" not in candidate
    assert candidate["evidence_url"] == "https://directory.example/portfolio"
    assert len(candidate["id"]) == 24


@pytest.mark.parametrize("url", [
    "https://example.com/", "https://linkedin.com/jobs/1", "http://example.com/careers",
    "https://127.0.0.1/careers", "https://jobs.lever.co.evil.example/team",
    "https://jobs.eu.lever.co/team", "https://small.example/contact",
    "https://small.example/international", "javascript:alert(1)",
])
def test_irrelevant_private_restricted_and_unsupported_links_not_proposed(url):
    assert source_candidate(url, "Team", "https://directory.example/") is None


def test_directory_extracts_relative_ats_and_feed_links_without_job_fabrication():
    text = '''<a href="https://jobs.ashbyhq.com/tinyteam/one">Tiny team openings</a>
    <a href="/careers?utm_source=portfolio">Our careers</a>
    <a href="/about">About</a><link rel="alternate" type="application/rss+xml" href="/news-feed">
    <a href="https://jobs.ashbyhq.com/tinyteam/two">Another role</a>'''
    rows = page_candidates(text, "https://incubator.example/portfolio")
    assert len(rows) == 3  # ATS board deduped regardless of role URL.
    assert {row["kind"] for row in rows} == {"ashby", "html", "feed"}
    assert all(row["verified"] is False for row in rows)
    assert all("location" not in row and "eligibility" not in row for row in rows)
    assert next(row for row in rows if row["kind"] == "html")["url"] == "https://incubator.example/careers"


def test_parser_and_cache_are_bounded_and_preserve_first_discovery():
    text = "".join(f'<a href="/careers/{i}">Team {i}</a>' for i in range(1000))
    assert len(page_links(text, "https://example.com")) == 200
    assert len(page_candidates(text, "https://example.com")) == 20
    original = source_candidate("https://example.com/careers", "Old", "https://example.com")
    original["discovered_at"] = "2026-01-01T00:00:00+00:00"
    refreshed = {**original, "company": "Updated", "discovered_at": "2026-02-01T00:00:00+00:00"}
    merged = merge_candidates([original], [refreshed])
    assert merged[0]["company"] == "Updated" and merged[0]["discovered_at"] == original["discovered_at"]


@pytest.mark.parametrize("title", ["Software Developer Trainee", "Research Assistant", "Graduate Engineer Trainee", "Trainee Data Engineer", "Project Assistant"])
def test_adjacent_titles_discovered_but_student_eligibility_requires_review(title):
    job = discovery._job(external_id="one", title=title, company="Small company", location="India",
                         url="https://example.com/job/1", description="Currently pursuing a Bachelor's degree. Graduation year 2029. Must be based in India.")
    assert job and job["adjacent_student_role"]
    assert evaluate(job, Profile(verified_fields=["graduation_year", "degree", "country"]).model_dump())["eligibility"] == "review"
    assert discovery._job(external_id="other", title="Sales Trainee Manager", company="Other", url="https://example.com/jobs/2") is None


def test_unstructured_links_cannot_overwrite_verified_ats_facts():
    previous = {"source": "ashby", "location": "Pune", "active": False, "description": "Verified content"}
    incoming = {"source": "html", "location": "Not specified", "active": True, "verification_status": "reference_only"}
    merged, verified = merge_opportunity_data(previous, incoming)
    assert not verified and merged["active"] is False and merged["location"] == "Pune"


def mocked_network(monkeypatch, responses):
    calls = []
    async def request(client, url, **kwargs):
        calls.append((url, kwargs))
        body = responses.get(url, "")
        if isinstance(body, dict):
            body = json.dumps(body)
        return httpx.Response(200, content=body, request=httpx.Request("GET", url))
    monkeypatch.setattr(discovery, "_request", request)
    return calls


def test_careers_index_follows_bounded_same_origin_links_and_keeps_missing_facts_unknown(monkeypatch):
    url = "https://small.example/careers"
    text = "".join(f'<a href="/jobs/{i}">Software Intern {i}</a>' for i in range(6))
    text += '<a href="https://elsewhere.example/job/1">Research Intern</a>'
    calls = mocked_network(monkeypatch, {url: text})
    result = asyncio.run(discovery.discover({"kind": "html", "url": url, "company": "Tiny studio", "permitted": True}))
    assert len(result["jobs"]) == 6
    assert len([call for call in calls if "/jobs/" in call[0]]) == 3
    assert all(call[1].get("robots") for call in calls if "/jobs/" in call[0])
    assert all(job["verification_status"] == "reference_only" and job["location"] == "Not specified" and job["deadline"] is None for job in result["jobs"])
    assert all(not job["application_url_verified"] for job in result["jobs"])
    assert result["cache"]["truncated"] is True


def test_search_discovers_incubator_boards_without_making_opportunities(monkeypatch):
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "synthetic-test-token")
    calls = []
    async def request(client, url, **kwargs):
        calls.append((url, kwargs))
        if url.startswith("https://api.search.brave.com/"):
            body = {"web": {"results": [{"title": "Nagpur incubator portfolio", "url": "https://incubator.example/portfolio"}]}}
            body = json.dumps(body)
        else:
            body = '<a href="https://jobs.lever.co/localteam/one">Local team</a><a href="http://127.0.0.1/careers">Bad</a>'
        return httpx.Response(200, content=body, request=httpx.Request("GET", url))
    monkeypatch.setattr(discovery, "_request", request)
    result = asyncio.run(discovery.discover({"kind": "search", "slug": "incubator portfolio Nagpur", "company": "Nagpur employer discovery", "permitted": True}))
    assert result["jobs"] == []
    assert len(result["cache"]["source_candidates"]) == 1
    candidate = result["cache"]["source_candidates"][0]
    assert candidate["slug"] == "localteam" and candidate["kind"] == "lever"
    assert "permitted" not in candidate and candidate["verified"] is False
    assert "freshness" not in parse_qs(urlsplit(calls[0][0]).query)
    assert calls[1][1]["robots"] is True
    assert "X-Subscription-Token" not in calls[1][1]["headers"]


def test_unverified_search_snippet_never_becomes_a_graduation_rejection():
    job = {"source":"search", "verification_status":"reference_only", "title":"Software internship",
           "description":"Graduating in 2027 only.", "requirements":{"graduation_years":[2027]}, "location":"Not specified"}
    result = evaluate(job, Profile(verified_fields=["graduation_year"]).model_dump())
    assert result["eligibility"] == "review"
    assert not any("2027" in statement for statement in result["verified"])


def test_existing_career_parent_and_ats_prevent_per_job_source_flooding():
    page = '<a href="/careers">Careers</a>' + ''.join(f'<a href="/careers/jobs/{i}">Role {i}</a>' for i in range(100))
    page += '<a href="https://jobs.ashbyhq.com/tinyteam/one">Apply</a>'
    proposals = page_candidates(page, "https://example.com/careers")
    assert len(proposals) == 2 and proposals[0]["kind"] == "ashby"
    assert proposals[1]["url"] == "https://example.com/careers"


def test_worker_persists_suggestions_and_dismissals_without_reverifying_plain_links(stack):  # noqa: F811
    client, account = stack.register()
    setup = '''
import asyncio, json
from sqlalchemy import select
from app import discovery
from app.database import SessionLocal
from app.models import Source, User
from app.services import process_discovery
from app.publisher_discovery import source_candidate
with SessionLocal() as db:
    owner = db.scalar(select(User)).id
    row = Source(owner_id=owner, kind='html', company='SYNTHETIC local studio', url='https://example.com/careers', enabled=True, permitted=True)
    db.add(row); db.commit(); source_id=row.id
async def discover(source, cache=None):
    jobs = [
        {'external_id':'test', 'title':'Software Intern', 'company':'Unverified publisher', 'url':'https://example.com/jobs/one', 'source':'html', 'verification_status':'reference_only', 'location':'Not specified', 'description':'', 'requirements':{}},
        {'external_id':'child', 'title':'Research Intern', 'company':'Verified child publisher', 'url':'https://example.com/jobs/two', 'source':'html', 'verification_status':'official_metadata_verified', 'verification_evidence_url':'https://example.com/jobs/two', 'location':'India', 'description':'Graduating in 2029.', 'requirements':{}},
    ]
    return {'jobs':jobs, 'cache':{'truncated':True, 'publisher_url':'https://example.com/careers', 'source_candidates':[source_candidate('https://jobs.ashbyhq.com/synthetic-team/one','Synthetic team','https://example.com/careers')]}, 'not_modified':False}
discovery.discover=discover
asyncio.run(process_discovery(owner, source_id))
print(json.dumps({'source_id':source_id}))
'''
    source_id = json.loads(stack.python(setup))["source_id"]
    suggestions = client.get("/api/discovery/source-candidates").json()
    assert suggestions["total"] == 1
    candidate_id = suggestions["items"][0]["id"]
    assert client.post(f"/api/discovery/source-candidates/{candidate_id}/dismiss").status_code == 200
    with stack.db() as db:
        db.execute("UPDATE opportunities SET last_verified='2000-01-01T00:00:00+00:00' WHERE json_extract(data, '$.source')='html'")
    # A new process simulates worker restart and a conditional 304 source result.
    stack.python('''
import asyncio
from sqlalchemy import select
from app import discovery
from app.database import SessionLocal
from app.models import Source
from app.services import process_discovery
with SessionLocal() as db:
    row = db.scalar(select(Source).where(Source.company=='SYNTHETIC local studio'))
    owner, source_id = row.owner_id, row.id
async def discover(source, cache=None):
    return {'jobs':[], 'cache':{'etag':'synthetic-unchanged'}, 'not_modified':True}
discovery.discover=discover
asyncio.run(process_discovery(owner, source_id))
''')
    assert client.get("/api/discovery/source-candidates").json()["total"] == 0
    with stack.db() as db:
        cache = json.loads(db.execute("SELECT cache FROM sources WHERE id=?", (source_id,)).fetchone()[0])
        assert cache["source_candidates"][0]["id"] == candidate_id
        assert candidate_id in cache["dismissed_source_candidate_ids"]
        verified_times = db.execute("SELECT last_verified FROM opportunities WHERE json_extract(data, '$.source')='html'").fetchall()
        assert len(verified_times) == 2
        assert all(row[0] == "2000-01-01T00:00:00+00:00" for row in verified_times)
