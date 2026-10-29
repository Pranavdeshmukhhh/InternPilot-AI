"""Fault injection uses synthetic records and httpx transports; no public traffic."""
import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import create_engine, select, func, text
from sqlalchemy.orm import sessionmaker

from app import coordination, services, worker, discovery
from app.database import Base
from app.models import Task, CoordinationState, RequestLease, DiscoveryHealth, CatalogSource


@pytest.fixture(params=["sqlite"] + (["postgresql"] if os.getenv("PHASE4_POSTGRES_URL") else []))
def lab(tmp_path, monkeypatch, request):
    schema = "phase5_" + uuid4().hex
    admin = None
    if request.param == "postgresql":
        admin = create_engine(os.environ["PHASE4_POSTGRES_URL"])
        with admin.begin() as c:
            c.execute(text('CREATE SCHEMA "' + schema + '"'))
        engine = create_engine(os.environ["PHASE4_POSTGRES_URL"], connect_args={"options":"-csearch_path=" + schema})
    else:
        engine = create_engine(f"sqlite:///{tmp_path / 'lab.db'}", connect_args={"timeout":30})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    for module in [coordination, services, worker]:
        monkeypatch.setattr(module, "SessionLocal", sessions)
    yield engine, sessions
    engine.dispose()
    if admin:
        with admin.begin() as c:
            c.execute(text('DROP SCHEMA "' + schema + '" CASCADE'))
        admin.dispose()


def test_queue_backpressure_idempotence_pause_and_recovery(lab, monkeypatch):
    _, sessions = lab
    monkeypatch.setattr(worker.settings, "queue_max_pending", 10)
    with sessions() as db:
        for i in range(10):
            services.enqueue(db,"owner","discovery",{},f"source:{i}")
        db.commit()
        assert services.enqueue(db,"owner","discovery",{},"source:0").id
        with pytest.raises(coordination.QueueCapacityError):
            services.enqueue(db,"owner","discovery",{},"overflow")
        db.rollback()
        db.add(CoordinationState(key="workers", value={"paused":True}));db.commit()
    assert worker.claim_task("paused") is None
    with sessions() as db:
        db.get(CoordinationState,"workers").value = {"paused":False};db.commit()
    task = worker.claim_task("dead-process")
    with sessions() as db:
        row = db.get(Task,task["id"])
        row.lease_until = "2000-01-01T00:00:00+00:00";db.commit()
    assert worker.recover_expired() == 1
    claimed = worker.claim_task("replacement")
    assert claimed["id"] == task["id"] and claimed["attempts"] == 2
    with sessions() as db:
        assert not services.valid_lease(db,task["id"],"dead-process")


def test_shared_failure_opens_circuit_for_other_subscribers(lab):
    from app.catalog import claim_public_scan
    _, sessions = lab
    with sessions() as db:
        row = CatalogSource(id="publisher",config={})
        db.add(row);db.commit()
        coordination.health_failure(db,row.id,discovery.DiscoveryError("429",retry_after=3600),300);db.commit()
        assert claim_public_scan(db,row,300)[0] == "backoff"
        h=db.get(DiscoveryHealth,row.id)
        assert datetime.fromisoformat(h.next_attempt) >= datetime.now(timezone.utc)+timedelta(seconds=3598)
        coordination.health_success(db,row.id);db.commit()
        assert claim_public_scan(db,row,300)[0] == "fetch"


def test_concurrent_http_slots_and_expired_process_capacity(lab, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    _, sessions = lab
    monkeypatch.setattr(worker.settings,"http_global_concurrency",4)
    monkeypatch.setattr(worker.settings,"http_host_concurrency",2)
    with ThreadPoolExecutor(max_workers=8) as pool:
        tokens=list(pool.map(coordination.request_slot,["same.example"]*8))
    admitted=[t for t in tokens if t]
    assert len(admitted) == 2
    other=[coordination.request_slot("other.example") for _ in range(4)]
    assert len([t for t in other if t]) == 2
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(RequestLease)) == 4
        for row in db.scalars(select(RequestLease)):
            row.expires_at="2000-01-01T00:00:00+00:00"
        db.commit()
    token=coordination.request_slot("same.example")
    assert token
    coordination.release_slot(token)


def test_workday_partial_checkpoint_retries_exact_failed_offset(monkeypatch):
    from app.pagination import workday_pages
    attempts=[];saved=[]
    async def request(client,url,**kwargs):
        offset=kwargs["payload"]["offset"];attempts.append(offset)
        if offset==40 and attempts.count(40)==1:
            raise discovery.DiscoveryError("network interrupted",retry_after=3600)
        return httpx.Response(200,json={"jobPostings":[{"externalPath":str(i)} for i in range(offset,min(offset+20,60))]})
    async def save(progress): saved.append(progress)
    monkeypatch.setattr(discovery,"_request",request)
    first={"total":60,"jobPostings":[{"externalPath":str(i)} for i in range(20)]}
    async def scenario():
        a=await workday_pages(None,"https://example.invalid",first,{}, {"_save_checkpoint":save},{})
        assert a[2] is True and len(a[0]["jobPostings"])==40 and a[3]==3600
        assert saved[-1]["offset"]==40
        b=await workday_pages(None,"https://example.invalid",first,{}, {"_pagination_checkpoint":saved[-1],"_save_checkpoint":save},{})
        assert b[2] is True  # Resumed offsets never prove a complete snapshot.
        assert len(b[0]["jobPostings"]) == 60  # Replays successful uncommitted pages, not just the failed page.
        assert attempts==[20,40,40] and b[1]["offset"]==20
    asyncio.run(scenario())


def test_1000_source_fixture_discovery_is_bounded(monkeypatch, tmp_path):
    """1,000 permitted fixture sources, real feed parser/request path, zero sockets."""
    import time
    active=peak=0
    requests=0
    real_client=httpx.AsyncClient
    async def handler(request):
        nonlocal active,peak,requests
        active+=1;peak=max(peak,active);requests+=1
        try:
            await asyncio.sleep(.001)
            if request.url.path=="/robots.txt":
                return httpx.Response(200,text="User-agent: *\nAllow: /")
            ident=request.url.path.rsplit("/",1)[-1]
            return httpx.Response(200,text=f'<rss><channel><item><title>Software Intern {ident}</title><link>https://opportunities.example.invalid/{ident}</link></item></channel></rss>')
        finally:
            active-=1
    async def public_fixture(url):return url
    async def no_throttle(*args):pass
    monkeypatch.setattr(discovery,"validate_public_url",public_fixture)
    monkeypatch.setattr("app.rate_limits.throttle",no_throttle)
    monkeypatch.setattr(discovery.httpx,"AsyncClient",lambda **kwargs: real_client(transport=httpx.MockTransport(handler),trust_env=False))
    monkeypatch.setattr(discovery,"_HOST_LOCKS",{})
    monkeypatch.setattr(discovery,"_HOST_DELAY",{f"fixture{i}.example.invalid":0 for i in range(50)})
    monkeypatch.setattr(worker.settings,"database_url","sqlite:///:memory:")
    monkeypatch.setattr(worker.settings,"http_global_concurrency",8)
    async def scenario():
        # Fixed workers; there is no task per source waiting on a semaphore.
        queue=asyncio.Queue(maxsize=32)
        results=[]
        async def consume():
            while True:
                i=await queue.get()
                try:
                    if i is None:return
                    r=await discovery.discover({"kind":"feed","url":f"https://fixture{i%50}.example.invalid/{i}","company":"Synthetic","permitted":True})
                    results.extend(r["jobs"])
                finally:queue.task_done()
        consumers=[asyncio.create_task(consume()) for _ in range(16)]
        for i in range(1000):await queue.put(i)
        for _ in consumers:await queue.put(None)
        await queue.join();await asyncio.gather(*consumers)
        assert len(results)==len({r['url'] for r in results})==1000
    start=time.perf_counter();asyncio.run(scenario());elapsed=time.perf_counter()-start
    assert peak<=8 and requests==2000
    # pytest retains the measured evidence; no production-capacity assertion.
    report={"sources":1000,"http_requests":requests,"peak_fixture_requests":peak,"seconds":elapsed,"transport":"httpx.MockTransport; no network", "production_capacity_claim":False}
    (tmp_path/'fixture-report.json').write_text(json.dumps(report))
    print(json.dumps(report))


def test_fair_dispatch_and_durable_inference_quota(lab, monkeypatch):
    _, sessions=lab
    with sessions() as db:
        for i in range(4):
            services.enqueue(db,"busy-owner","discovery",{},f"busy-{i}",priority=100)
        services.enqueue(db,"small-owner","discovery",{},"small",priority=0)
        db.commit()
    first=worker.claim_task("one")
    second=worker.claim_task("two")
    assert first["owner_id"]=="busy-owner" and second["owner_id"]=="small-owner"
    monkeypatch.setattr(worker.settings,"llm_daily_request_limit",2)
    assert coordination.reserve_inference()
    assert coordination.reserve_inference()
    assert not coordination.reserve_inference()


def test_duplicate_read_task_execution_keeps_one_effect(lab, monkeypatch):
    _, sessions=lab
    with sessions() as db:
        services.enqueue(db,"owner","discovery",{},"same-intent");db.commit()
    claimed=worker.claim_task("worker")
    effects=[]
    async def guarded(owner, source, **kwargs):
        with sessions() as db:
            if services.valid_lease(db,kwargs["task_id"],kwargs["lease_owner"]):
                effects.append(owner)
    monkeypatch.setattr(worker,"process_discovery",guarded)
    asyncio.run(worker.execute_task(claimed,"worker"))
    asyncio.run(worker.execute_task(claimed,"worker"))
    assert effects==["owner"]
    with sessions() as db:
        row=db.get(Task,claimed["id"])
        row.status="running";row.lease_owner="worker";row.attempts+=1;row.lease_until=(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat();db.commit()
    asyncio.run(worker.execute_task(claimed,"worker"))
    assert effects==["owner"]


def test_network_recovery_retry_after_and_access_denial(monkeypatch):
    delays=[];calls=0
    async def permitted_fixture(url):return url
    async def cooldown(host,seconds):delays.append(seconds)
    async def handler(request):
        nonlocal calls
        calls+=1
        if calls==1:raise httpx.ReadTimeout("synthetic network loss")
        if calls==2:return httpx.Response(503,headers={"Retry-After":"120"})
        if calls==3:return httpx.Response(403)
        return httpx.Response(200,json={"ok":True})
    monkeypatch.setattr(discovery,"validate_public_url",permitted_fixture)
    monkeypatch.setattr("app.rate_limits.cooldown",cooldown)
    monkeypatch.setattr(discovery,"_HOST_DELAY",{"failure.example.invalid":0})
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(discovery.DiscoveryError):
                await discovery._request(client,"https://failure.example.invalid")
            with pytest.raises(discovery.DiscoveryError) as caught:
                await discovery._request(client,"https://failure.example.invalid")
            assert caught.value.retry_after==120 and delays==[120]
            discovery._HOST_DELAY["failure.example.invalid"]=0
            with pytest.raises(discovery.DiscoveryError) as denied:
                await discovery._request(client,"https://failure.example.invalid")
            assert denied.value.permanent
            assert (await discovery._request(client,"https://failure.example.invalid")).json()=={"ok":True}
    asyncio.run(scenario())


def test_cancelled_http_operation_releases_database_permit(lab, monkeypatch):
    _,sessions=lab
    monkeypatch.setattr(worker.settings,"database_url","postgresql+psycopg://fixture")
    async def scenario():
        started=asyncio.Event()
        async def operation():
            async with coordination.http_slot("cancel.example.invalid"):
                started.set()
                await asyncio.Event().wait()
        task=asyncio.create_task(operation())
        await started.wait()
        task.cancel()
        await asyncio.gather(task,return_exceptions=True)
    asyncio.run(scenario())
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(RequestLease))==0


def test_expired_lease_cannot_acknowledge_unprocessed_task(lab, monkeypatch):
    _,sessions=lab
    with sessions() as db:
        services.enqueue(db,"owner","discovery",{},"expired-ack");db.commit()
    claimed=worker.claim_task("expired")
    with sessions() as db:
        db.get(Task,claimed["id"]).lease_until="2000-01-01T00:00:00+00:00";db.commit()
    async def declined(*args,**kwargs):return
    monkeypatch.setattr(worker,"process_discovery",declined)
    asyncio.run(worker.execute_task(claimed,"expired"))
    with sessions() as db:
        assert db.get(Task,claimed["id"]).status=="running"
    assert worker.recover_expired()==1
    with sessions() as db:
        assert db.get(Task,claimed["id"]).status=="queued"


def test_1000_sources_durable_scheduler_deduplicates_batches(lab, monkeypatch):
    from app.models import User, Source
    from app.security import encrypt
    _,sessions=lab
    monkeypatch.setattr(worker.settings,"crawl_batch_size",1000)
    with sessions() as db:
        for owner in range(20):
            ident=f"scheduler-owner-{owner}"
            db.add(User(id=ident,email_hash=ident,email_encrypted=encrypt("synthetic@example.invalid"),password_hash="synthetic",
                policy_encrypted=encrypt({"emergency_stop":False}),profile_encrypted=encrypt({})))
            db.add_all([Source(id=f"scheduled-{owner}-{i}",owner_id=ident,kind="feed",company="Synthetic",permitted=True,enabled=True) for i in range(50)])
        db.commit()
    assert worker.schedule_due()==1000
    assert worker.schedule_due()==0
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(Task))==1000
        assert db.scalar(select(func.count(func.distinct(Task.dedupe_key))))==1000
