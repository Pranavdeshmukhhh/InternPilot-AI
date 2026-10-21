"""Worker/automatic-preparation regressions with isolated databases and no network."""
import asyncio
import io
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker

from app import discovery, services, worker
from app.database import Base
from app.matching import extract_requirements
from app.models import Application, Document, Opportunity, Source, SourceOpportunity, Task, User, now
from app.schemas import Policy, Profile
from app.security import decrypt, decrypt_bytes, digest, encrypt
from pypdf import PdfReader


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'worker.sqlite3'}", connect_args={"timeout":20})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(services, "SessionLocal", sessions)
    monkeypatch.setattr(worker, "SessionLocal", sessions)

    def account(**overrides):
        profile = Profile(name="Verified Candidate", email="verified@example.invalid",
                          degree="Bachelor of Technology", university="Verified University",
                          skills=["Python", "SQL"],
                          verified_fields=["name", "email", "country", "graduation_year", "degree", "university", "skills"]).model_dump()
        policy = {**Policy(mode="assisted").model_dump(), "auto_prepare":True,
                  "preparation_minimum_score":0, "daily_preparation_limit":10, **overrides}
        with sessions() as db:
            user = User(email_hash=digest(str(overrides)), email_encrypted=encrypt(profile["email"]),
                        password_hash="test-only", profile_encrypted=encrypt(profile), policy_encrypted=encrypt(policy))
            db.add(user)
            db.flush()
            source = Source(owner_id=user.id, kind="greenhouse", slug="fixture", company="Fixture Employer",
                            enabled=True, permitted=True, interval_seconds=300)
            db.add(source)
            db.commit()
            return user.id, source.id

    def posting(owner, source, label, **overrides):
        description = "Currently pursuing a Bachelor's degree, graduating in 2029. Must be based in India. Python and SQL."
        data = {"title":"Software Engineering Intern", "company":"Fixture Employer", "location":"India",
                "url":f"https://jobs.example.invalid/{label}", "description":description,
                "requirements":extract_requirements(description), "skills":["Python", "SQL"],
                "deadline":None, "active":True, **overrides}
        with sessions() as db:
            job = Opportunity(fingerprint=digest(owner + label), data=data)
            db.add(job)
            db.flush()
            db.add(SourceOpportunity(source_id=source, opportunity_id=job.id))
            db.commit()
            return job.id

    yield SimpleNamespace(sessions=sessions, account=account, posting=posting)
    engine.dispose()


@pytest.mark.parametrize("policy_change", [
    {"auto_prepare":False}, {"mode":"discovery"}, {"emergency_stop":True},
])
def test_automatic_preparation_requires_opt_in_and_clear_policy(isolated, policy_change):
    owner, source = isolated.account(**policy_change)
    isolated.posting(owner, source, "eligible")
    assert services.queue_automatic_preparation(owner) == 0
    with isolated.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Application)) == 0


def test_automatic_preparation_reacts_to_verified_profile_without_rescanning(isolated):
    owner, source = isolated.account()
    job_id = isolated.posting(owner, source, "eligible")
    with isolated.sessions() as db:
        user = db.get(User, owner)
        profile = decrypt(user.profile_encrypted)
        profile["verified_fields"].remove("university")
        user.profile_encrypted = encrypt(profile)
        db.commit()
    assert services.queue_automatic_preparation(owner) == 0
    with isolated.sessions() as db:
        user = db.get(User, owner)
        profile["verified_fields"].append("university")
        user.profile_encrypted = encrypt(profile)
        db.commit()
    assert services.queue_automatic_preparation(owner) == 1
    assert services.queue_automatic_preparation(owner) == 0
    with isolated.sessions() as db:
        app = db.scalar(select(Application))
        task = db.scalar(select(Task))
        assert app.opportunity_id == job_id and app.status == "queued"
        assert app.approved_at is None and app.submission_started_at is None
        assert task.payload == {"application_id":app.id, "automatic_preparation":True}


def test_daily_budget_counts_manual_apps_and_filters_before_choosing_urgent_candidate(isolated):
    owner, source = isolated.account(daily_preparation_limit=2)
    already = isolated.posting(owner, source, "already")
    isolated.posting(owner, source, "wrong-year", description="Currently pursuing a Bachelor's degree, graduating in 2028. Must be based in India. Python and SQL.")
    later = isolated.posting(owner, source, "later", deadline=(datetime.now(timezone.utc)+timedelta(days=20)).isoformat())
    urgent = isolated.posting(owner, source, "urgent", deadline=(datetime.now(timezone.utc)+timedelta(hours=5)).isoformat())
    with isolated.sessions() as db:
        db.add(Application(owner_id=owner, opportunity_id=already, status="awaiting_review"))
        # A demo created today must not consume a real preparation slot.
        db.add(Application(owner_id=owner, opportunity_id="local-demo", is_demo=True))
        db.commit()
    assert services.queue_automatic_preparation(owner) == 1
    assert services.queue_automatic_preparation(owner) == 0
    with isolated.sessions() as db:
        apps = list(db.scalars(select(Application).where(Application.is_demo == False)))
        assert {app.opportunity_id for app in apps} == {already, urgent}
        assert later not in {app.opportunity_id for app in apps}
        assert db.scalar(select(Task)).priority >= 1000


def test_concurrent_schedulers_share_daily_budget_and_prevent_duplicates(isolated):
    owner, source = isolated.account(daily_preparation_limit=2)
    for index in range(4):
        isolated.posting(owner, source, str(index))
    with ThreadPoolExecutor(max_workers=2) as pool:
        counts = list(pool.map(lambda _:services.queue_automatic_preparation(owner), range(2)))
    assert sum(counts) == 2
    with isolated.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Application)) == 2
        assert db.scalar(select(func.count()).select_from(Task)) == 2


@pytest.mark.parametrize("restriction", ["consent", "company", "origin", "score", "permission", "stale"])
def test_automatic_mode_retains_all_restrictions(isolated, restriction):
    options = {"mode":"auto", "auto_consent":True, "allowed_companies":["Fixture Employer"],
               "allowed_origins":["https://jobs.example.invalid"], "minimum_score":0}
    if restriction == "consent": options["auto_consent"] = False
    if restriction == "company": options["allowed_companies"] = ["Another Employer"]
    if restriction == "origin": options["allowed_origins"] = ["https://another.example.invalid"]
    if restriction == "score": options["preparation_minimum_score"] = 100
    owner, source = isolated.account(**options)
    job_id = isolated.posting(owner, source, "eligible")
    with isolated.sessions() as db:
        if restriction == "score":
            posting = db.get(Opportunity,job_id)
            posting.data = {**posting.data,"skills":["Rust"]}
        if restriction == "permission": db.get(Source, source).permitted = False
        if restriction == "stale": db.get(Opportunity, job_id).last_verified = (datetime.now(timezone.utc)-timedelta(days=3)).isoformat()
        db.commit()
    assert services.queue_automatic_preparation(owner) == 0


def test_automatic_task_rechecks_policy_before_browser(isolated, monkeypatch):
    owner, source = isolated.account()
    isolated.posting(owner, source, "eligible")
    assert services.queue_automatic_preparation(owner) == 1
    with isolated.sessions() as db:
        user = db.get(User, owner)
        policy = decrypt(user.policy_encrypted)
        policy["auto_prepare"] = False
        user.policy_encrypted = encrypt(policy)
        db.commit()

    async def forbidden_browser(**kwargs):
        pytest.fail("A revoked automatic policy must be checked before opening a browser")

    monkeypatch.setattr("app.automation.run_application", forbidden_browser)
    task = worker.claim_task("policy-recheck")
    asyncio.run(worker.execute_task(task, "policy-recheck"))
    with isolated.sessions() as db:
        assert db.scalar(select(Application)).status == "needs_input"
        assert db.scalar(select(Task)).status == "completed"


def test_automatic_preparation_generates_verified_pdf_and_stops_at_review(isolated, monkeypatch):
    owner, source = isolated.account()
    isolated.posting(owner, source, "eligible")
    assert services.queue_automatic_preparation(owner) == 1

    async def forbidden_browser(**kwargs):
        pytest.fail("Automatic drafting must never visit a form or upload personal documents")

    monkeypatch.setattr("app.automation.run_application", forbidden_browser)
    task = worker.claim_task("preparation-worker")
    asyncio.run(worker.execute_task(task, "preparation-worker"))
    with isolated.sessions() as db:
        application = db.scalar(select(Application))
        assert application.status == "awaiting_review"
        assert application.document_id is not None
        assert application.submission_started_at is None and application.confirmation_id is None
        assert application.approved_at is None
        document = db.get(Document, application.document_id)
        pdf = decrypt_bytes(document.content_encrypted)
        assert pdf.startswith(b"%PDF-")
        text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)
        assert "Verified Candidate" in text
        assert "Verified University" in text
        assert "Python" in text
        assert application.screenshot_id is None and application.session_encrypted is None
        assert db.scalar(select(Task)).status == "completed"


def test_historical_permitted_source_link_does_not_allow_automatic_preparation(isolated):
    owner, source = isolated.account()
    job_id = isolated.posting(owner, source, "removed-from-permitted-source")
    with isolated.sessions() as db:
        db.get(Source, source).cache = {"active_opportunity_ids":[]}
        other = Source(owner_id=owner, kind="greenhouse", slug="old", company="Disabled Employer",
                       enabled=False, permitted=False, cache={"active_opportunity_ids":[job_id]})
        db.add(other)
        db.flush()
        db.add(SourceOpportunity(source_id=other.id, opportunity_id=job_id))
        db.commit()
    assert services.queue_automatic_preparation(owner) == 0


def test_source_retry_cannot_bypass_backoff_but_runs_when_due(isolated, monkeypatch):
    owner, source_id = isolated.account(auto_prepare=False)
    scans = []

    async def scan(source, cache=None):
        scans.append(source["id"])
        return {"jobs":[], "cache":{}, "not_modified":False}

    monkeypatch.setattr(discovery, "discover", scan)
    with isolated.sessions() as db:
        source = db.get(Source, source_id)
        source.failures, source.status = 1, "error"
        source.next_run = (datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
        db.commit()
    asyncio.run(services.process_discovery(owner, source_id))
    worker.schedule_due()
    assert scans == []
    with isolated.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Task)) == 0
        db.get(Source, source_id).next_run = "2000-01-01T00:00:00+00:00"
        db.commit()
    worker.schedule_due()
    task = worker.claim_task("retry-worker")
    asyncio.run(worker.execute_task(task, "retry-worker"))
    assert scans == [source_id]
    with isolated.sessions() as db:
        assert db.get(Source, source_id).failures == 0
        assert db.scalar(select(Task)).status == "completed"


def test_emergency_stop_prevents_already_queued_discovery(isolated, monkeypatch):
    owner, source_id = isolated.account(emergency_stop=True)

    async def forbidden_scan(*args, **kwargs):
        pytest.fail("Emergency stop must stop queued discovery before network activity")

    monkeypatch.setattr(discovery, "discover", forbidden_scan)
    asyncio.run(services.process_discovery(owner, source_id))
    worker.schedule_due()
    with isolated.sessions() as db:
        assert db.get(Source, source_id).last_attempt is None
        assert db.scalar(select(func.count()).select_from(Task)) == 0


def test_housekeeping_and_unhandled_task_errors_do_not_stop_worker(monkeypatch, caplog, tmp_path):
    async def scenario():
        stopped = asyncio.Event()
        presence = []
        executed = []
        monkeypatch.setattr(worker.asyncio, "Event", lambda:stopped)
        monkeypatch.setattr(asyncio.get_running_loop(), "add_signal_handler", lambda *args:None)
        monkeypatch.setattr(worker, "migrate", lambda:None)
        monkeypatch.setattr(worker.settings, "worker_heartbeat_file", str(tmp_path / "missing" / "heartbeat"))

        def broken(*args, **kwargs):
            raise OSError("sensitive exception text must not appear in operational logs")

        def presence_failure(*args, **kwargs):
            presence.append(kwargs.get("stopped", False))
            broken()

        monkeypatch.setattr(worker, "record_heartbeat", presence_failure)
        for name in ("schedule_deadline_reminders", "recover_expired", "schedule_due", "queue_automatic_preparation"):
            monkeypatch.setattr(worker, name, broken)
        claims = iter([{"id":"durable-task"}, None])
        monkeypatch.setattr(worker, "claim_task", lambda _:next(claims, None))

        async def failed_execution(task, worker_id):
            executed.append(task["id"])
            stopped.set()
            raise RuntimeError("durable recovery transaction failed")

        monkeypatch.setattr(worker, "execute_task", failed_execution)
        await worker.run_worker()
        assert executed == ["durable-task"]
        assert presence == [False, True]

    asyncio.run(scenario())
    assert "Task execution interrupted" in caplog.text
    assert "supervisor heartbeat failed" in caplog.text
    assert "sensitive exception text" not in caplog.text


def test_worker_failure_requeues_only_before_submission_checkpoint(isolated, monkeypatch):
    owner, source = isolated.account(auto_prepare=False)
    ids = []
    with isolated.sessions() as db:
        for checkpoint in (False, True):
            app = Application(owner_id=owner, opportunity_id=str(checkpoint), status="submitting" if checkpoint else "preparing",
                              submission_started_at=now() if checkpoint else None)
            db.add(app)
            db.flush()
            task = services.enqueue(db, owner, "application", {"application_id":app.id}, f"application:{app.id}")
            ids.append((app.id, task.id))
        db.commit()

    async def broken_application(*args, **kwargs):
        raise RuntimeError("transient task failure")

    monkeypatch.setattr(worker, "process_application", broken_application)
    for _ in ids:
        task = worker.claim_task("failure-worker")
        asyncio.run(worker.execute_task(task, "failure-worker"))
    with isolated.sessions() as db:
        safe_app, safe_task = ids[0]
        uncertain_app, uncertain_task = ids[1]
        assert db.get(Task, safe_task).status == "queued"
        assert db.get(Task, safe_task).available_at > now()
        assert db.get(Task, uncertain_task).status == "failed"
        assert db.get(Application, uncertain_app).status == "uncertain"
        assert worker.claim_task("another-worker") is None


def test_lease_recovery_never_requeues_after_checkpoint(isolated):
    owner, source = isolated.account(auto_prepare=False)
    with isolated.sessions() as db:
        app = Application(owner_id=owner, opportunity_id="checkpoint", status="submitting", submission_started_at=now())
        db.add(app)
        db.flush()
        task = services.enqueue(db, owner, "application", {"application_id":app.id}, f"application:{app.id}")
        task.status, task.lease_owner, task.lease_until = "running", "expired-worker", "2000-01-01T00:00:00+00:00"
        db.commit()
        app_id, task_id = app.id, task.id
    assert worker.recover_expired() == 1
    with isolated.sessions() as db:
        assert db.get(Application, app_id).status == "uncertain"
        assert db.get(Task, task_id).status == "completed"
        assert db.get(Task, task_id).lease_owner is None


def test_worker_failure_after_upload_checkpoint_never_requeues(isolated, monkeypatch):
    owner, _ = isolated.account(auto_prepare=False)
    with isolated.sessions() as db:
        app = Application(owner_id=owner,opportunity_id="approved-upload",status="preparing",upload_started_at=now())
        db.add(app); db.flush()
        task = services.enqueue(db,owner,"application",{"application_id":app.id},f"application:{app.id}")
        app_id,task_id = app.id,task.id
        db.commit()
    async def failure(*args,**kwargs):
        raise RuntimeError("synthetic failure after file assignment")
    monkeypatch.setattr(worker,"process_application",failure)
    claimed = worker.claim_task("upload-worker")
    asyncio.run(worker.execute_task(claimed,"upload-worker"))
    with isolated.sessions() as db:
        assert db.get(Task,task_id).status == "failed"
        assert db.get(Application,app_id).status == "uncertain"
        assert worker.claim_task("retry-worker") is None
