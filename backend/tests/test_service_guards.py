"""Regression coverage for discovery isolation and pre-parser request limits.

Discovery HTTP calls and optional model calls are replaced at their network
boundaries. The real service transaction, normalization, persistence and ranking
paths run against a separate database for every test.
"""
from __future__ import annotations

import asyncio
import copy
import io
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker

from app import discovery, llm, services
from app.body_limit import BodyLimitMiddleware
from app.database import Base
from app.matching import extract_requirements
from app.models import Application, Document, Opportunity, Source, Task, User, now
from app.schemas import Policy, Profile
from app.security import approval_digest, decrypt, decrypt_bytes, digest, encrypt


def run(coro):
    return asyncio.run(coro)


def job(company="Verified employer", year=2029):
    description = (
        f"Currently pursuing a Bachelor's degree, graduating in {year}. "
        "Must be based in India. Python and SQL."
    )
    return {
        "external_id": "same-official-requisition",
        "title": "Software Engineering Intern",
        "company": company,
        "location": "India",
        "remote": False,
        "url": "https://jobs.example.invalid/official-requisition-1",
        "description": description,
        "skills": ["Python", "SQL"],
        "requirements": extract_requirements(description),
        "published_at": None,
        "deadline": None,
        "compensation": None,
    }


@pytest.fixture
def isolated_services(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'service-guards.sqlite3'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(services, "SessionLocal", sessions)
    monkeypatch.setenv("LLM_PROVIDER", "disabled")

    def add_account(label):
        profile = Profile(
            name="Private candidate name",
            email=f"{label}@private.example.invalid",
            degree="B.Tech Computer Science",
            skills=["Python", "SQL"],
            verified_fields=["name", "email", "country", "graduation_year", "degree", "skills"],
        ).model_dump()
        with sessions() as db:
            account = User(
                email_hash=digest(profile["email"]),
                email_encrypted=encrypt(profile["email"]),
                password_hash="unused-test-only-hash",
                profile_encrypted=encrypt(profile),
                policy_encrypted=encrypt(Policy().model_dump()),
            )
            db.add(account)
            db.flush()
            source = Source(
                owner_id=account.id,
                kind="greenhouse",
                slug="test-fixture",
                company=label,
                permitted=True,
                enabled=True,
                interval_seconds=300,
            )
            db.add(source)
            db.commit()
            return account.id, source.id

    yield SimpleNamespace(sessions=sessions, add_account=add_account)
    engine.dispose()


def test_discovery_data_is_owner_isolated_and_still_deduplicates(isolated_services, monkeypatch):
    first_owner, first_source = isolated_services.add_account("first-employer")
    second_owner, second_source = isolated_services.add_account("second-employer")
    replacements = {}

    async def discover(source, cache=None):
        return {
            "jobs": [job(source["company"], replacements.get(source["id"], 2029))],
            "cache": {},
            "not_modified": False,
        }

    monkeypatch.setattr(discovery, "discover", discover)
    run(services.process_discovery(first_owner, first_source))
    run(services.process_discovery(second_owner, second_source))
    replacements[second_source] = 2028
    run(services.process_discovery(second_owner, second_source))
    run(services.process_discovery(first_owner, first_source))

    with isolated_services.sessions() as db:
        first = services.visible_jobs(db, first_owner)
        second = services.visible_jobs(db, second_owner)
        assert len(first) == len(second) == 1
        assert first[0].id != second[0].id
        assert first[0].data["company"] == "first-employer"
        assert first[0].data["requirements"]["graduation_years"] == [2029]
        assert second[0].data["company"] == "second-employer"
        assert second[0].data["requirements"]["graduation_years"] == [2028]
        assert db.scalar(select(func.count()).select_from(Opportunity)) == 2
        assert db.get(Source, first_source).status == "healthy"
        assert db.get(Source, second_source).status == "healthy"


@pytest.mark.parametrize("reference_kind",["internscan","search"])
def test_stale_aggregator_reference_cannot_keep_removed_employer_posting_open(isolated_services, monkeypatch, reference_kind):
    from app.models import SourceOpportunity
    owner,source_id = isolated_services.add_account("closure")
    published = True
    async def discover(source,cache=None):
        return {"jobs":[job()] if published else [],"cache":{},"not_modified":False}
    monkeypatch.setattr(discovery,"discover",discover)
    run(services.process_discovery(owner,source_id))
    with isolated_services.sessions() as db:
        existing = services.visible_jobs(db,owner)[0]
        reference = Source(owner_id=owner,kind=reference_kind,company="Stale reference feed",permitted=True,enabled=True,
                           cache={"active_opportunity_ids":[existing.id],"reference_feed":True})
        db.add(reference);db.flush()
        db.add(SourceOpportunity(source_id=reference.id,opportunity_id=existing.id))
        db.commit()
    published = False
    run(services.process_discovery(owner,source_id))
    with isolated_services.sessions() as db:
        existing = services.visible_jobs(db,owner)[0]
        assert existing.data["active"] is False
        profile = decrypt(db.get(User,owner).profile_encrypted)
        assert services.job_view(existing,profile)["status"] == "closed"


def test_not_modified_refreshes_verification_without_changing_first_discovery(isolated_services, monkeypatch):
    owner_id, source_id = isolated_services.add_account("cached-employer")

    async def discover(source, cache=None):
        if cache and cache.get("etag") == "unchanged-board":
            return {"jobs": [], "cache": cache, "not_modified": True}
        return {"jobs": [job()], "cache": {"etag": "unchanged-board"}, "not_modified": False}

    monkeypatch.setattr(discovery, "discover", discover)
    run(services.process_discovery(owner_id, source_id))
    with isolated_services.sessions() as db:
        posting = services.visible_jobs(db, owner_id)[0]
        first_discovered = posting.first_discovered
        posting.last_verified = (datetime.now(timezone.utc) - timedelta(days=4)).isoformat()
        db.commit()
        assert services.job_view(posting, Profile().model_dump())["eligibility"] == "review"

    before_refresh = datetime.now(timezone.utc)
    run(services.process_discovery(owner_id, source_id))
    with isolated_services.sessions() as db:
        posting = services.visible_jobs(db, owner_id)[0]
        assert services.timestamp(posting.last_verified) >= before_refresh
        assert posting.first_discovered == first_discovered
        assert db.get(Source, source_id).status == "healthy"
        assert db.get(Source, source_id).discovered_count == 1
        assert db.scalar(select(func.count()).select_from(Opportunity)) == 1


def test_search_cache_does_not_refresh_unfetched_publisher_metadata(isolated_services, monkeypatch):
    owner,source_id = isolated_services.add_account("cached-search")
    with isolated_services.sessions() as db:
        db.get(Source,source_id).kind = "search"
        db.commit()
    async def discover(source,cache=None):
        if cache:
            return {"jobs":[],"cache":cache,"not_modified":True}
        return {"jobs":[{**job(),"source":"search","verification_status":"official_metadata_verified"}],"cache":{"etag":"search-cached","truncated":True},"not_modified":False}
    monkeypatch.setattr(discovery,"discover",discover)
    run(services.process_discovery(owner,source_id))
    old = "2001-01-01T00:00:00+00:00"
    with isolated_services.sessions() as db:
        services.visible_jobs(db,owner)[0].last_verified = old
        db.commit()
    run(services.process_discovery(owner,source_id))
    with isolated_services.sessions() as db:
        assert services.visible_jobs(db,owner)[0].last_verified == old


def test_closed_listing_stays_inactive_and_is_not_refreshed_by_later_304(isolated_services, monkeypatch):
    owner_id, source_id = isolated_services.add_account("closed-listing-employer")
    remaining = job()
    removed = copy.deepcopy(remaining)
    removed["external_id"] = "removed-official-requisition"
    removed["url"] = "https://jobs.example.invalid/removed-requisition-2"
    scan_count = 0

    async def discover(source, cache=None):
        nonlocal scan_count
        scan_count += 1
        if scan_count == 1:
            return {"jobs": [copy.deepcopy(remaining), copy.deepcopy(removed)], "cache": {"etag": "two-listings"}, "not_modified": False}
        if scan_count == 2:
            return {"jobs": [copy.deepcopy(remaining)], "cache": {"etag": "one-listing"}, "not_modified": False}
        assert cache["etag"] == "one-listing"
        return {"jobs": [], "cache": cache, "not_modified": True}

    monkeypatch.setattr(discovery, "discover", discover)
    run(services.process_discovery(owner_id, source_id))
    removed_last_verified = "2001-01-01T00:00:00+00:00"
    with isolated_services.sessions() as db:
        postings = services.visible_jobs(db, owner_id)
        assert len(postings) == 2
        by_external_id = {posting.data["external_id"]: posting for posting in postings}
        removed_id = by_external_id[removed["external_id"]].id
        remaining_id = by_external_id[remaining["external_id"]].id
        for posting in postings:
            posting.last_verified = removed_last_verified
        db.commit()

    run(services.process_discovery(owner_id, source_id))
    with isolated_services.sessions() as db:
        closed = db.get(Opportunity, removed_id)
        active = db.get(Opportunity, remaining_id)
        assert closed.data["active"] is False
        assert closed.last_verified == removed_last_verified
        assert active.data.get("active", True) is True
        assert set(db.get(Source, source_id).cache["active_opportunity_ids"]) == {remaining_id}
        active.last_verified = "2002-01-01T00:00:00+00:00"
        db.commit()

    before_304 = datetime.now(timezone.utc)
    run(services.process_discovery(owner_id, source_id))
    with isolated_services.sessions() as db:
        closed = db.get(Opportunity, removed_id)
        active = db.get(Opportunity, remaining_id)
        assert closed.data["active"] is False
        assert closed.last_verified == removed_last_verified
        assert services.job_view(closed, Profile().model_dump())["eligibility"] == "ineligible"
        assert active.data.get("active", True) is True
        assert services.timestamp(active.last_verified) >= before_304
        assert db.get(Source, source_id).status == "healthy"
        assert scan_count == 3


@pytest.mark.parametrize("retry_after", [3600, 86400])
def test_source_retry_respects_server_delay_larger_than_local_backoff(isolated_services, monkeypatch, retry_after):
    owner_id, source_id = isolated_services.add_account("rate-limited-employer")

    async def discover(source, cache=None):
        raise discovery.DiscoveryError("Rate limited", retry_after=retry_after)

    monkeypatch.setattr(discovery, "discover", discover)
    before_attempt = datetime.now(timezone.utc)
    run(services.process_discovery(owner_id, source_id))
    with isolated_services.sessions() as db:
        source = db.get(Source, source_id)
        assert source.status == "error"
        assert source.failures == 1
        assert services.timestamp(source.next_run) >= before_attempt + timedelta(seconds=retry_after)
        assert db.scalar(select(func.count()).select_from(Opportunity)) == 0


def test_model_suggestion_cannot_replace_persisted_official_requirements(isolated_services, monkeypatch):
    owner_id, source_id = isolated_services.add_account("llm-employer")
    official = job(year=2028)
    original_requirements = copy.deepcopy(official["requirements"])
    prompts = []

    async def discover(source, cache=None):
        return {"jobs": [copy.deepcopy(official)], "cache": {}, "not_modified": False}

    async def analyze(description, **kwargs):
        prompts.append(description)
        return {
            "status": "available",
            "verified": False,
            "requirements": [{"kind": "graduation_year", "value": "2029", "evidence": "2028", "verified": False}],
            "warnings": [],
        }

    monkeypatch.setattr(discovery, "discover", discover)
    monkeypatch.setattr(llm, "analyze_requirements", analyze)
    monkeypatch.setattr(llm, "_ANALYSIS_CACHE", OrderedDict())
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    run(services.process_discovery(owner_id, source_id))
    with isolated_services.sessions() as db:
        posting = services.visible_jobs(db, owner_id)[0]
        assert posting.data["requirements"] == original_requirements
        assert posting.data["llm_analysis"]["verified"] is False
        assert posting.data["llm_analysis"]["status"] == "skipped"
        from app.security import decrypt
        profile = decrypt(db.get(User, owner_id).profile_encrypted)
        assert services.job_view(posting, profile)["eligibility"] == "ineligible"
    assert prompts == []  # Rejected eligibility is filtered before any paid model call.


def test_oversized_chunked_multipart_rejected_before_parser_or_remaining_chunks():
    parser_called = False
    consumed = 0
    sent = []
    one_mib = b"x" * (1024 * 1024)
    chunks = [b'--fixture\r\nContent-Disposition: form-data; name="file"; filename="large.pdf"\r\n\r\n']
    chunks.extend([one_mib] * 12)
    chunks.append(b"\r\n--fixture--\r\n")

    async def parser_app(scope, receive, send):
        nonlocal parser_called
        parser_called = True
        raise AssertionError("Oversized multipart must not reach the upload parser")

    async def receive():
        nonlocal consumed
        chunk = chunks[consumed]
        consumed += 1
        return {"type": "http.request", "body": chunk, "more_body": consumed < len(chunks)}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "scheme": "http", "method": "POST", "path": "/api/documents/upload",
        "raw_path": b"/api/documents/upload", "query_string": b"",
        # Deliberately no Content-Length: the byte limit must also protect chunks.
        "headers": [(b"content-type", b"multipart/form-data; boundary=fixture"), (b"transfer-encoding", b"chunked")],
        "client": ("127.0.0.1", 1234), "server": ("127.0.0.1", 8000),
    }
    run(BodyLimitMiddleware(parser_app)(scope, receive, send))
    assert parser_called is False
    assert consumed < len(chunks)
    assert next(message for message in sent if message["type"] == "http.response.start")["status"] == 413
    assert b"9 MiB" in b"".join(message.get("body", b"") for message in sent)


def queued_application(isolated_services, label, approve_upload=False):
    owner_id, _ = isolated_services.add_account(label)
    with isolated_services.sessions() as db:
        owner = db.get(User, owner_id)
        owner.policy_encrypted = encrypt(Policy(mode="assisted").model_dump())
        posting = Opportunity(fingerprint=digest(label + ":application-fixture"), data=job())
        db.add(posting)
        db.flush()
        application = Application(owner_id=owner_id, opportunity_id=posting.id, status="queued")
        db.add(application)
        db.flush()
        if approve_upload:
            from app.documents import generate_resume
            profile = decrypt(owner.profile_encrypted)
            document = services.store_document(db,owner_id,generate_resume(profile,posting.data),"resume",posting.id)
            application.document_id = document.id
            application.snapshot_encrypted = encrypt({"profile":profile,"job":posting.data,"policy":Policy(mode="assisted").model_dump()})
            application.upload_approved_at = now()
            application.upload_approval_digest = approval_digest(profile,posting.data,document.id)
        task = Task(
            owner_id=owner_id, kind="application",
            dedupe_key=f"application:{application.id}", payload={"application_id": application.id},
            status="running", lease_owner="original-worker",
            lease_until=(datetime.now(timezone.utc) + timedelta(minutes=3)).isoformat(),
        )
        db.add(task)
        db.commit()
        return owner_id, application.id, task.id


@pytest.mark.parametrize("replacement_confirmed", [False, True])
@pytest.mark.parametrize("stale_raises", [False, True])
def test_stale_worker_cannot_overwrite_replacement_result_or_confirmed_submission(
    isolated_services, monkeypatch, replacement_confirmed, stale_raises,
):
    _, application_id, task_id = queued_application(isolated_services, "lease-isolation",approve_upload=True)
    expected_status = "submitted" if replacement_confirmed else "preparing"
    expected_reason = "Result owned by the replacement worker"
    confirmation = "TEST-ABCD01234567" if replacement_confirmed else None

    async def stale_browser(**kwargs):
        # The original browser is still running when its lease is transferred.
        # Simulate the replacement's newer durable state before it returns.
        with isolated_services.sessions() as db:
            task = db.get(Task, task_id)
            task.lease_owner = "replacement-worker"
            task.status = "completed" if replacement_confirmed else "running"
            application = db.get(Application, application_id)
            application.status = expected_status
            application.reason = expected_reason
            application.confirmation_id = confirmation
            if replacement_confirmed:
                application.submission_started_at = now()
                application.confirmation_encrypted = encrypt({"text": "Authoritative replacement confirmation"})
            db.commit()
        if stale_raises:
            raise OSError("The abandoned browser exited late")
        return {"status": "needs_input", "reason": "Stale worker result must be ignored"}

    monkeypatch.setattr("app.automation.run_application", stale_browser)
    run(services.process_application(application_id, task_id=task_id, lease_owner="original-worker"))
    with isolated_services.sessions() as db:
        application = db.get(Application, application_id)
        assert application.status == expected_status
        assert application.reason == expected_reason
        assert application.confirmation_id == confirmation
        assert db.get(Task, task_id).lease_owner == "replacement-worker"
        if replacement_confirmed:
            assert decrypt(application.confirmation_encrypted)["text"] == "Authoritative replacement confirmation"


def test_restart_with_corrected_profile_regenerates_document_and_invalidates_approval(isolated_services, monkeypatch):
    from app.documents import generate_resume
    from pypdf import PdfReader

    owner_id, application_id, task_id = queued_application(isolated_services, "corrected-profile")
    with isolated_services.sessions() as db:
        owner = db.get(User, owner_id)
        old_profile = decrypt(owner.profile_encrypted)
        old_profile["projects"] = [{"name": "Removed inaccurate project", "description": "Candidate later corrected this fact", "skills": []}]
        old_profile["verified_fields"] = [*old_profile["verified_fields"], "projects"]
        application = db.get(Application, application_id)
        posting = db.get(Opportunity, application.opportunity_id)
        old_document = services.store_document(db, owner_id, generate_resume(old_profile, posting.data), "resume", posting.id)
        old_document_id = old_document.id
        application.document_id = old_document.id
        application.snapshot_encrypted = encrypt({"profile": old_profile, "job": posting.data, "policy": Policy(mode="assisted").model_dump()})
        application.approved_at = now()
        application.approval_digest = approval_digest(old_profile, posting.data, old_document.id)
        application.status = "approved"
        corrected = copy.deepcopy(old_profile)
        corrected["name"] = "Corrected Verified Candidate"
        corrected["projects"] = []
        owner.profile_encrypted = encrypt(corrected)
        db.commit()

    observed = []

    async def inspect_prepared_package(**kwargs):
        observed.append(kwargs)
        with isolated_services.sessions() as db:
            application = db.get(Application, application_id)
            assert application.document_id != old_document_id
            assert application.approved_at is None
            assert application.approval_digest is None
            assert decrypt(application.snapshot_encrypted)["profile"] == corrected
        return {"status": "awaiting_review", "reason": "New factual document needs candidate review"}

    monkeypatch.setattr("app.automation.run_application", inspect_prepared_package)
    run(services.process_application(application_id, task_id=task_id, lease_owner="original-worker"))
    assert observed == []  # Corrected facts require a new, specific upload approval.
    with isolated_services.sessions() as db:
        updated_application = db.get(Application,application_id)
        updated_document = db.get(Document,updated_application.document_id)
        new_pdf = decrypt_bytes(updated_document.content_encrypted)
        assert decrypt(updated_application.snapshot_encrypted)["profile"] == corrected
    pdf_text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(new_pdf)).pages)
    assert "Corrected Verified Candidate" in pdf_text
    assert "Removed inaccurate project" not in pdf_text
    with isolated_services.sessions() as db:
        application = db.get(Application, application_id)
        new_document = db.get(Document, application.document_id)
        assert new_document.version == 2
        assert new_document.id != old_document_id
        assert decrypt_bytes(new_document.content_encrypted) == new_pdf
        assert db.get(Document, old_document_id).version == 1
        assert application.approved_at is None and application.approval_digest is None
        assert application.status == "awaiting_review"
