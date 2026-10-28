"""Regional discovery never substitutes location preference for legal eligibility."""
import asyncio
import json

import httpx
import pytest

from app import discovery
from app.geography import classify, location_matches
from app.matching import evaluate
from app.regional_search import search_sources
from app.schemas import Profile
from app.services import merge_opportunity_data
from test_api_worker import stack  # noqa: F401 -- pytest fixture
from test_platform_upgrade import posting, seed


@pytest.mark.parametrize("location,expected", [
    ("Nagpur", {"local", "india"}), ("Pune, Maharashtra", {"local", "india"}),
    ("Hinjewadi", {"local", "india"}), ("Butibori", {"local", "india"}),
    ("Bengaluru", {"india"}), ("Remote - United States", {"international"}),
    ("Singapore", {"international"}), ("Worldwide", {"worldwide"}),
    ("Remote", {"unknown"}), ("Not specified", {"unknown"}),
    ("Indiana", {"unknown"}), ("Puneville", {"unknown"}),
    ("Pune / Berlin", {"local", "india", "international"}),
])
def test_regions_use_location_metadata(location, expected):
    assert set(classify({"location":location},{})["regions"]) == expected


def test_no_country_assumed_from_company_description_query_or_remote_flag():
    data = {"title":"India Software Intern", "company":"Pune Labs", "location":"Remote", "remote":True,
            "description":"Indian students welcome; head office in Germany.", "discovery_query":"internship Nagpur"}
    assert classify(data,{})["regions"] == ["unknown"]
    assert classify({"location":"San Francisco, CA"},{})["countries"] == ["United States"]
    assert classify({"location":"Virtual", "venue_country":"IN"},{})["regions"] == ["india"]


def test_editable_local_cities_and_nearby_clusters():
    assert classify({"location":"MIHAN"},{})["local_matches"] == ["Nagpur"]
    assert classify({"location":"MIHAN"},{"include_nearby_locations":False})["regions"] == ["india"]
    assert classify({"location":"Mumbai"},{"preferred_local_cities":["Mumbai"]})["regions"] == ["local","india"]
    assert not classify({"location":"Pune"},{"preferred_local_cities":[]})["local_matches"]
    assert location_matches({"location":"Pimpri-Chinchwad"},"Pune")
    assert not location_matches({"location":"Hinjawadi"},"Pune",False)
    assert location_matches({"location":"Bangalore"},"India")
    assert Profile(preferred_local_cities=[" Pune ","pune","Nagpur",""]).preferred_local_cities == ["Pune","Nagpur"]
    with pytest.raises(ValueError):
        Profile(preferred_local_cities=["x"*101])


def test_local_preference_does_not_override_rejection_or_unknown_authorization():
    profile = Profile().model_dump()
    rejected = evaluate({"location":"Pune", "description":"Interns graduating in 2027 only."},profile)
    assert rejected["eligibility"] == "ineligible" and rejected["score"] <= 24
    overseas = evaluate({"location":"Remote - USA", "remote":True,"description":"Software internship. Must be based in United States."},profile)
    assert overseas["eligibility"] == "ineligible"
    assert evaluate({"location":"Worldwide", "remote":True,"description":"Software internship."},profile)["eligibility"] == "review"


def test_region_search_templates_cover_both_types_and_respect_custom_preferences():
    defaults = search_sources()
    assert len(defaults) >= 8 and len({s["slug"] for s in defaults}) == len(defaults)
    assert all(len(s["slug"])<=200 and s["interval_seconds"]>=1800 for s in defaults)
    assert any("Pune" in s["slug"] and "hackathon" in s["slug"] for s in defaults)
    assert any("Indian students" in s["slug"] and "internship" in s["slug"] for s in defaults)
    custom = search_sources({"preferred_local_cities":["Mumbai"],"include_nearby_locations":False})
    assert len(custom) < len(defaults) and any('"Mumbai"' in s["slug"] for s in custom)
    assert not any("Pune" in s["slug"] for s in custom)


def test_search_snippets_cannot_erase_official_location_or_reopen_closed_postings():
    official = {"source":"greenhouse","location":"Pune","active":False,"deadline":"2099-01-01T00:00:00Z"}
    reference = {"source":"search","location":"Not specified","active":True,"verification_status":"reference_only"}
    merged,verified = merge_opportunity_data(official,reference)
    assert merged["location"]=="Pune" and merged["active"] is False and verified is False
    publisher = {**official,"source":"search","verification_status":"official_metadata_verified"}
    merged,verified = merge_opportunity_data(publisher,reference)
    assert merged["location"]=="Pune" and verified is False


def test_region_api_filters_both_types_pagination_and_saved(stack):  # noqa: F811
    client,_ = stack.register()
    source = client.get("/api/sources").json()[0]["id"]
    records = [posting(str(index), location=place, description="Software intern. Verify eligibility.", opportunity_type=kind)
               for kind in ("internship","hackathon")
               for index,place in enumerate(("Nagpur", "Hinjawadi", "Bengaluru", "Berlin", "Remote", "Worldwide"))]
    # Unique identities across both types in this synthetic test.
    for index,row in enumerate(records):
        row["url"] += f"/{index}"
    ids = seed(stack,source,records)
    for kind in ("internship","hackathon"):
        def query(**params):
            return client.get("/api/opportunities/page",params={"kind":kind,**params}).json()
        assert query(region="local")["total"]==2
        assert query(region="india")["total"]==3
        assert query(region="international")["total"]==1
        assert query(region="unknown")["total"]==1
        assert query(region="worldwide")["total"]==1
        assert query(region="local",location="Pune")["items"][0]["location"]=="Hinjawadi"
        assert query(region="local",page_size=1,page=2)["total"]==2
        assert query(location="India")["total"]==3
    assert client.get("/api/opportunities?region=invalid").status_code==422
    assert client.get("/api/opportunities?region=international").json()[0]["geography"]["countries"]==["Germany"]
    assert client.post("/api/saved/"+ids[0]).status_code==200
    assert client.get("/api/opportunities/page?saved=true&region=local").json()["total"]==1
    profile = client.get("/api/profile").json()
    assert client.put("/api/profile",json={**profile,"preferred_local_cities":["Bengaluru"]}).status_code==200
    assert client.get("/api/opportunities/page?region=local").json()["total"]==2
    config = client.get("/api/discovery/regions").json()
    assert config["local_cities"]==["Bengaluru"]
    assert any("Bengaluru" in p["slug"] for p in config["search_presets"])
    assert json.loads(stack.python("from app.database import SessionLocal; from app.models import User; from app.security import decrypt; from sqlalchemy import select; import json;\nwith SessionLocal() as db: print(json.dumps(decrypt(db.scalar(select(User)).profile_encrypted)['preferred_local_cities']))"))==["Bengaluru"]


@pytest.mark.parametrize("stack",[{"BRAVE_SEARCH_API_KEY":""},{"BRAVE_SEARCH_API_KEY":"synthetic-key-no-network"}],indirect=True)
def test_enable_regional_search_reports_missing_key_and_is_idempotent(stack):  # noqa: F811
    client,_ = stack.register()
    other,_ = stack.register("other@example.invalid")
    configured = bool(stack.env["BRAVE_SEARCH_API_KEY"])
    config = client.get("/api/discovery/regions").json()
    assert config["search_configured"] is configured
    assert "synthetic-key" not in json.dumps(config)
    response = client.post("/api/discovery/regions/enable")
    if not configured:
        assert response.status_code==409 and "BRAVE_SEARCH_API_KEY" in response.text
        assert not any(s["kind"]=="search" for s in client.get("/api/sources").json())
    else:
        expected = len(search_sources())
        assert response.status_code==200 and response.json()["added"]==expected
        assert client.post("/api/discovery/regions/enable").json()["added"]==0
        assert len([s for s in client.get("/api/sources").json() if s["kind"]=="search"])==expected
        assert not any(s["kind"]=="search" for s in other.get("/api/sources").json())


def test_search_verifies_local_internship_and_hackathon_without_sending_search_key(monkeypatch):
    calls = []
    async def request(client,url,**kwargs):
        calls.append((url,kwargs))
        if "api.search.brave.com" in url:
            return httpx.Response(200,json={"web":{"results":[
                {"title":"Software Internship", "url":"https://publisher.example/intern", "description":"Search snippet"},
                {"title":"AI Hackathon", "url":"https://publisher.example/hack", "description":"Search snippet"},
                {"title":"Internship reference", "url":"https://publisher.example/unknown", "description":"Pune India"},
                {"title":"Hackathon fourth", "url":"https://publisher.example/fourth", "description":"Nagpur"},
            ]}},request=httpx.Request("GET",url))
        metadata = {"@type":"JobPosting","title":"Software Internship","url":url,"hiringOrganization":{"name":"Publisher"},
                    "jobLocation":{"address":{"addressLocality":"Pune","addressCountry":"IN"}},"description":"Public software internship."} if url.endswith("intern") else {
                    "@type":"Event","name":"AI Hackathon","url":url,"organizer":{"name":"Publisher"},
                    "location":{"address":{"addressLocality":"Nagpur","addressCountry":"IN"}},"description":"AI hackathon."}
        if url.endswith("unknown"):
            return httpx.Response(200,text="No structured metadata",request=httpx.Request("GET",url))
        return httpx.Response(200,text='<script type="application/ld+json">'+json.dumps(metadata)+'</script>',request=httpx.Request("GET",url))
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY","synthetic-search-key")
    monkeypatch.setattr(discovery,"_request",request)
    result = asyncio.run(discovery.discover({"kind":"search","permitted":True,"slug":"Pune internships hackathons","company":"Regional"}))
    jobs = result["jobs"]
    assert len(jobs)==4 and jobs[1]["opportunity_type"]=="hackathon"
    assert classify(jobs[0],{})["local_matches"]==["Pune"]
    assert classify(jobs[1],{})["local_matches"]==["Nagpur"]
    assert jobs[1]["registration_status"]=="unknown"
    assert jobs[2]["verification_status"]=="reference_only" and classify(jobs[2],{})["regions"]==["unknown"]
    assert jobs[3]["location"]=="Not specified"
    assert len(calls)==4 and result["cache"]["truncated"] is True
    for _,kwargs in calls[1:]:
        assert kwargs["robots"] is True and "X-Subscription-Token" not in kwargs["headers"]
