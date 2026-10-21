"""Integrated opportunity workflows through a real isolated API process.

Only synthetic data is used. No test enables an external upload or message.
"""
import json
from datetime import datetime, timedelta, timezone

from test_api_worker import stack  # noqa: F401 -- pytest fixture registration


def seed(stack, source_id, records):
    script = '''
import json
from app.database import SessionLocal
from app.models import Opportunity, SourceOpportunity, Source
from app.security import digest
from app.matching import extract_requirements
from app.services import canonical_fingerprint
records = json.loads(RECORDS)
ids = []
with SessionLocal() as db:
    owner = db.get(Source,SOURCE).owner_id
    for index,data in enumerate(records):
        data.setdefault("requirements",extract_requirements(data.get("description","")))
        row = Opportunity(fingerprint=digest(owner+":"+canonical_fingerprint(data)),data=data)
        db.add(row); db.flush()
        db.add(SourceOpportunity(source_id=SOURCE,opportunity_id=row.id))
        ids.append(row.id)
    db.commit()
print(json.dumps(ids))
'''.replace("RECORDS",repr(json.dumps(records))).replace("SOURCE",repr(source_id))
    return json.loads(stack.python(script))


def posting(label, **changes):
    return {"title":"Software Engineering Intern "+label,"company":"Synthetic Employer",
            "url":"https://careers.example.invalid/"+label,"location":"India","remote":True,
            "description":"Currently pursuing a Bachelor's degree, graduating in 2029. Must be based in India. Python.",
            "skills":["Python"],"active":True,"source":"greenhouse",**changes}


def verified_profile(client):
    profile = client.get("/api/profile").json()
    profile.update(name="Synthetic Test Candidate",email="synthetic@example.invalid",degree="B.Tech Computer Science",
                   university="Synthetic University",skills=["Python"],
                   verified_fields=["name","email","country","graduation_year","degree","university","skills"])
    assert client.put("/api/profile",json=profile).status_code == 200
    policy = client.get("/api/policy").json()
    assert client.put("/api/policy",json={**policy,"mode":"assisted"}).status_code == 200


def test_real_pagination_filters_expiry_timezone_and_saved_persistence(stack):
    owner,_ = stack.register()
    other,_ = stack.register("other@example.invalid")
    source = owner.get("/api/sources").json()[0]["id"]
    future = (datetime.now(timezone.utc)+timedelta(days=2)).isoformat()
    rows = [posting(str(i),deadline=future) for i in range(23)]
    rows += [posting("expired",deadline="2020-01-01T00:00:00+05:30"),posting("closed",active=False),
             posting("hack",opportunity_type="hackathon",title="Synthetic AI Hackathon",requirements={},
                     eligibility="Open to all students worldwide",registration_status="unknown"),
             posting("ineligible",description="Students graduating in 2027 only.",requirements={"graduation_years":[2027]})]
    ids = seed(stack,source,rows)
    first = owner.get("/api/opportunities/page",params={"kind":"internship","page_size":20}).json()
    second = owner.get("/api/opportunities/page",params={"kind":"internship","page":2,"page_size":20}).json()
    assert first["total"] == 24 and len(first["items"]) == 20 and len(second["items"]) == 4
    assert not set(j["id"] for j in first["items"]) & set(j["id"] for j in second["items"])
    hacks = owner.get("/api/opportunities/page?kind=hackathon").json()
    assert hacks["total"] == 1 and hacks["items"][0]["status"] == "unverified"
    assert owner.get("/api/opportunities?search=ineligible&eligibility=ineligible").json()[0]["id"] == ids[-1]
    assert len(owner.get("/api/opportunities?include_closed=true").json()) == 27
    assert owner.get("/api/opportunities/page?page_size=101").status_code == 422
    assert owner.get("/api/opportunities?deadline_before=not-a-date").status_code == 422
    assert len(owner.get("/api/opportunities?deadline_before=2021-01-01&include_closed=true").json()) == 1
    assert owner.post("/api/saved/"+ids[0]).status_code == 200
    assert owner.post("/api/saved/"+ids[0]).status_code == 200
    assert other.post("/api/saved/"+ids[0]).status_code == 404
    assert other.get("/api/saved").json() == []
    assert len(owner.get("/api/saved").json()) == 1
    # Delete source provenance; an explicitly saved opportunity remains owned
    # and readable, including after a fresh process opens the persisted DB.
    assert owner.delete("/api/sources/"+source).status_code == 200
    assert owner.get("/api/opportunities/"+ids[0]).status_code == 200
    assert len(owner.get("/api/saved").json()) == 1
    assert stack.python("from app.database import SessionLocal; from app.models import SavedOpportunity; from sqlalchemy import select;\nwith SessionLocal() as db: print(len(db.scalars(select(SavedOpportunity)).all()))") == "1"
    assert owner.delete("/api/saved/"+ids[0]).status_code == 200
    assert owner.get("/api/saved").json() == []


def test_import_deduplicates_per_account_and_preserves_verified_facts(stack):
    owner,_ = stack.register()
    other,_ = stack.register("other@example.invalid")
    source = owner.get("/api/sources").json()[0]["id"]
    ids = seed(stack,source,[posting("existing",deadline="2099-01-01T00:00:00Z")])
    exports = [{"title":"Software Engineering Intern", "company":"Wrong Aggregator Name",
                "job_url":"https://careers.example.invalid/existing?utm_source=export", "deadline":"2098-01-01T00:00:00Z"},
               {"title":"AI Intern", "company":"Synthetic Employer","job_url":"https://careers.example.invalid/new", "is_remote":False},
               {"title":"Senior Engineer","company":"Example","job_url":"https://careers.example.invalid/senior"}]
    def upload(client):
        return client.post("/api/imports/opportunities?provider=jobspy",files={"file":("jobs.json",json.dumps(exports).encode(),"application/json")})
    first = upload(owner)
    assert first.status_code == 200,first.text
    assert {key:first.json()[key] for key in ("added","updated","skipped")} == {"added":1,"updated":1,"skipped":1}
    assert upload(owner).json()["added"] == 0
    existing = owner.get("/api/opportunities/"+ids[0]).json()
    assert existing["company"] == "Synthetic Employer" and existing["deadline"] == "2099-01-01T00:00:00Z"
    imported = owner.get("/api/opportunities?search=AI%20Intern").json()[0]
    assert imported["status"] == "unverified" and imported["remote"] is False
    assert upload(other).json()["added"] == 2
    assert other.get("/api/opportunities/"+ids[0]).status_code == 404
    assert owner.post("/api/imports/opportunities?provider=jobspy",files={"file":("bad.json",b"not json")}).status_code == 422


def test_preparation_waits_for_specific_upload_approval_and_rejects_changed_facts(stack):
    owner,_ = stack.register()
    other,_ = stack.register("other@example.invalid")
    verified_profile(owner)
    source = owner.get("/api/sources").json()[0]["id"]
    ids = seed(stack,source,[posting("consent")])
    response = owner.post("/api/applications",json={"opportunity_id":ids[0]})
    assert response.status_code == 200,response.text
    app_id = response.json()["id"]
    assert owner.post("/api/applications",json={"opportunity_id":ids[0]}).status_code == 409
    assert stack.worker_once()["kind"] == "application"
    prepared = owner.get("/api/applications").json()[0]
    assert prepared["status"] == "awaiting_review" and prepared["upload_supported"]
    assert prepared["document_id"] and not prepared["upload_started_at"] and not prepared["confirmation_id"]
    assert owner.get("/api/documents/"+prepared["document_id"]+"/download").content.startswith(b"%PDF-")
    assert other.post(f"/api/applications/{app_id}/approve-upload",json={"consent":True}).status_code == 404
    assert owner.post(f"/api/applications/{app_id}/approve-upload",json={"consent":False}).status_code == 422
    assert owner.post(f"/api/applications/{app_id}/approve",json={"consent":True}).status_code == 409
    checklist = owner.get(f"/api/applications/{app_id}/checklist").json()
    assert checklist["missing_profile_fields"] == [] and checklist["confirmation_id"] is None
    profile = owner.get("/api/profile").json()
    assert owner.put("/api/profile",json={**profile,"name":"Corrected Verified Candidate"}).status_code == 200
    assert owner.post(f"/api/applications/{app_id}/approve-upload",json={"consent":True}).status_code == 409
    assert owner.post(f"/api/applications/{app_id}/retry").status_code == 200
    stack.worker_once()
    assert owner.post(f"/api/applications/{app_id}/approve-upload",json={"consent":True}).status_code == 200
    # Approval is recorded but NOT executed against the synthetic external URL.
    with stack.db() as db:
        row = db.execute("SELECT * FROM applications WHERE id=?",(app_id,)).fetchone()
        assert row["upload_approved_at"] and not row["upload_started_at"]
        db.execute("UPDATE applications SET upload_started_at='2026-01-01T00:00:00+00:00',status='preparing' WHERE id=?",(app_id,))
        db.execute("UPDATE tasks SET status='running',lease_owner='stopped-worker',lease_until='2000-01-01T00:00:00+00:00' WHERE kind='application'")
    assert stack.recover() == 1
    assert owner.get("/api/applications").json()[0]["status"] == "uncertain"
    assert owner.post(f"/api/applications/{app_id}/retry").status_code == 409
    assert owner.post(f"/api/applications/{app_id}/approve-upload",json={"consent":True}).status_code == 409


def test_notification_settings_drafts_are_committed_and_owner_scoped(stack):
    owner,_ = stack.register()
    other,_ = stack.register("other@example.invalid")
    prefs = owner.get("/api/notification-settings").json()
    assert prefs["delivery_config"] == {"browser":True,"email":False,"telegram":False,"whatsapp":False}
    assert owner.put("/api/notification-settings",json={"timezone":"Invalid/Zone"}).status_code == 422
    saved = owner.put("/api/notification-settings",json={"browser_enabled":True,"quiet_hours_enabled":True,"timezone":"Asia/Kolkata"})
    assert saved.status_code == 200 and saved.json()["browser_enabled"]
    assert owner.get("/api/notification-settings").json()["quiet_hours_enabled"]
    assert not other.get("/api/notification-settings").json()["browser_enabled"]
    assert owner.get("/api/notification-deliveries").json() == []
    assert owner.post("/api/notification-deliveries/nonexistent/send",json={"consent":True}).status_code == 404


def test_paid_filter_requires_positive_compensation_or_a_disclosed_prize(stack):
    owner,_ = stack.register()
    source = owner.get("/api/sources").json()[0]["id"]
    ids = seed(stack,source,[posting("paid",compensation="INR 10000 / month"),
        posting("unknown",compensation="Not disclosed"),posting("unpaid",compensation="Unpaid"),
        posting("zero",compensation="INR 0"),
        posting("prize",opportunity_type="hackathon",title="Synthetic Hackathon",description="Cash prizes of INR 50000.",requirements={}),
        posting("maybe",opportunity_type="hackathon",title="Synthetic Hackathon",description="Prizes may be available; amounts TBD.",requirements={})])
    result = owner.get("/api/opportunities?paid=true").json()
    assert {row["id"] for row in result} == {ids[0],ids[4]}
