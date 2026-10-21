"""Interoperability is read-only; fixtures never contact a job platform."""
import asyncio
import json

import httpx
import pytest

from app import aggregation, discovery
from app.services import merge_opportunity_data


def record(**changes):
    return {"title":"Software Engineering Intern", "company":"Synthetic Employer",
            "job_url":"https://careers.example.invalid/jobs/123?utm_source=export",
            "description":"Undergraduate internship for students graduating in 2029. Python.",
            "location":"India", **changes}


@pytest.mark.parametrize("filename,content", [
    ("jobs.json", json.dumps([record()])),
    ("jobs.jsonl", json.dumps(record())+"\n"),
    ("jobs.csv", "title,company,job_url,is_remote\nSoftware Engineering Intern,Synthetic Employer,https://careers.example.invalid/jobs/123,false\n"),
])
def test_authorized_export_formats_and_false_remote(filename, content):
    rows = aggregation.records_from_bytes(content.encode(),filename)
    result = aggregation.normalize_record(rows[0],"jobspy_feed")
    assert result["url"] == "https://careers.example.invalid/jobs/123"
    assert result["verification_status"] == "unverified"
    assert result["application_url_verified"] is False
    if filename.endswith(".csv"):
        assert result["remote"] is False
    else:
        assert result["remote"] is None


@pytest.mark.parametrize("url", ["http://example.com/job", "https://127.0.0.1/apply",
    "https://192.168.1.3/apply", "https://localhost/apply", "https://host.internal/apply",
    "https://user:password@example.com/apply", "https://www.linkedin.com/jobs/view/123", None, {}])
def test_unsafe_or_restricted_references_are_skipped(url):
    assert aggregation.normalize_record(record(job_url=url),"jobspy_feed") is None


@pytest.mark.parametrize("change", [{"title":{"value":"intern"}}, {"company":["Example"]},
                                      {"title":"Senior Software Engineer"}, {"company":""}])
def test_malformed_or_non_intern_records_are_skipped(change):
    assert aggregation.normalize_record(record(**change),"internscan") is None


def test_dates_do_not_invent_timezones_or_deadlines_and_nan_is_not_money():
    result = aggregation.normalize_record(record(date_posted="2026-10-21",deadline="2026-11-01",
        min_amount="NaN",max_amount="Infinity",currency="INR",is_remote=False),"internscan")
    assert result["published_at"] is None and result["published_date"] == "2026-10-21"
    assert result["deadline"] is None and result["deadline_raw"] == "2026-11-01"
    assert result["compensation"] is None and result["remote"] is False
    exact = aggregation.normalize_record(record(deadline="2026-11-01T00:30:00+05:30"),"internscan")
    assert exact["deadline"] == "2026-10-31T19:00:00+00:00"


@pytest.mark.parametrize("content,filename", [(b"not json","jobs.json"), (b"{}","jobs.exe"),
    (b"\xff","jobs.csv"), (b'"scalar"',"jobs.json"), (b"[]"*(aggregation.MAX_IMPORT_BYTES//2+1),"jobs.json")])
def test_invalid_imports_fail_with_reviewable_error(content,filename):
    with pytest.raises(ValueError):
        aggregation.records_from_bytes(content,filename)


def test_reference_cannot_overwrite_employer_facts():
    official = {**record(),"source":"greenhouse","verification_status":"verified","deadline":"2027-01-01T00:00:00Z"}
    incoming = aggregation.normalize_record(record(deadline="2028-01-01T00:00:00Z"),"jobspy_feed")
    merged, refreshed = merge_opportunity_data(official,incoming)
    assert refreshed is False
    assert merged["deadline"] == official["deadline"]
    assert merged["source"] == "greenhouse" and merged["discovered_via"] == ["jobspy_feed"]


def test_feed_conditional_cache_and_robots_boundary(monkeypatch):
    calls = []
    async def request(client,url,**kwargs):
        calls.append(kwargs)
        if kwargs["headers"].get("If-None-Match") == "synthetic-etag":
            return httpx.Response(304,headers={"etag":"synthetic-etag"},request=httpx.Request("GET",url))
        return httpx.Response(200,json=[record()],headers={"etag":"synthetic-etag"},request=httpx.Request("GET",url))
    monkeypatch.setattr(discovery,"_request",request)
    source = {"kind":"internscan","permitted":True}
    result = asyncio.run(aggregation.discover_aggregation(source))
    assert result["cache"]["reference_feed"] and len(result["jobs"]) == 1
    cached = asyncio.run(aggregation.discover_aggregation(source,result["cache"]))
    assert cached["not_modified"] and cached["jobs"] == []
    assert all(call["robots"] is True for call in calls)


def test_feed_requires_explicit_read_only_permission():
    with pytest.raises(discovery.DiscoveryError):
        asyncio.run(aggregation.discover_aggregation({"kind":"internscan","permitted":False}))
