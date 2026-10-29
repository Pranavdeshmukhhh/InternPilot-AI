"""Actual persistence/queues/filters; no live network submissions or email."""
import importlib.util
import io
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidTag
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import rate_limits, worker
from app.database import Base
from app.discovery_filters import DiscoveryCriteria, disclosed_details, matches
from app.models import CrawlRun, HostBudget
from test_api_worker import stack  # noqa: F401 -- fixture
from test_platform_upgrade import posting, seed


def test_disclosed_stipend_and_duration_do_not_guess_experience_or_foreign_pay():
    assert disclosed_details({'description':'Minimum 6 months experience.','compensation':'USD 1000 / month'})['duration_min_months'] is None
    facts=disclosed_details({'description':'Internship duration: 3 months.','compensation':'INR 15,000–20,000 per month'})
    assert facts['duration_min_months']==3 and facts['monthly_stipend_min_inr']==15000
    assert disclosed_details({'description':'6-month internship.','compensation':'INR 600000 per year'})['monthly_stipend_min_inr'] is None
    assert not matches({'requirements':{},'skills':[]},DiscoveryCriteria(graduation_year=2029))


def test_qualification_filters_paginate_and_preserve_unknowns(stack):  # noqa: F811
    client,_=stack.register()
    source=client.get('/api/sources').json()[0]['id']
    rows=[posting('matching',description="Currently pursuing a Bachelor's degree, graduating in 2029. Internship duration: 6 months. Must be based in India. Python and SQL.",skills=['Python','SQL'],compensation='INR 20000 / month'),
          posting('wrong-year',description="Undergraduate students graduating in 2027. Internship duration: 6 months. Python.",compensation='INR 20000 / month'),posting('unknown',description='Software internship. Python.',compensation=None)]
    ids=seed(stack,source,rows)
    response=client.get('/api/opportunities/page',params={'skills':'Python,SQL','graduation_year':2029,'degree_level':'undergraduate','duration_min':3,'stipend_min':15000})
    assert response.status_code==200,response.text
    assert response.json()['total']==1 and response.json()['items'][0]['id']==ids[0]
    assert client.get('/api/opportunities?stipend_min=25000').json()==[]
    assert client.get('/api/opportunities?duration_min=-1').status_code==422
    assert client.get('/api/opportunities?degree_level=invented').status_code==422
    assert client.get('/api/opportunities?graduation_year=2051').status_code==422


def test_thousand_source_bulk_import_dedup_manual_fanout_and_tenant_isolation(stack):  # noqa: F811
    client,_=stack.register();other,_=stack.register('other@example.invalid')
    existing=len(client.get('/api/sources').json())
    sources=[{'kind':'greenhouse','slug':f'synthetic-{i}','company':'SYNTHETIC offline source configuration','permitted':True,'enabled':True} for i in range(1000)]
    first=client.post('/api/sources/bulk',json={'sources':sources})
    assert first.status_code==200,first.text
    assert first.json()['added']==1000 and first.json()['skipped']==0
    assert client.post('/api/sources/bulk',json={'sources':sources}).json()['added']==0
    assert len(other.get('/api/sources').json())==existing
    queued=client.post('/api/discovery/run')
    assert queued.status_code==200 and queued.json()['queued_sources']==1000+existing
    assert client.post('/api/discovery/run').json()['queued_sources']==1000+existing
    with stack.db() as db:
        assert db.execute("SELECT count(*) FROM tasks WHERE kind='discovery'").fetchone()[0]==1000+existing
    assert client.post('/api/sources/bulk',json={'sources':sources+[sources[0]]}).status_code==422
    operations=client.get('/api/operations').json()
    assert operations['sources']==1000+existing and operations['worker']['queued']==1000+existing
    assert operations['recent_scans']==[] and operations['p95_seconds'] is None
    assert other.get('/api/operations').json()['worker']['queued']==0


def test_source_catalog_distinguishes_live_checked_api_from_key_required_search(stack):  # noqa: F811
    client,_=stack.register()
    catalog=client.get('/api/sources/catalog').json()
    startup=next(row for row in catalog if row['key']=='sarvam-ai')
    assert startup['installed'] and startup['source']['slug']=='sarvam'
    before=len(client.get('/api/sources').json())
    assert client.post('/api/sources/catalog/sarvam-ai').status_code==200
    assert len(client.get('/api/sources').json())==before
    assert client.post('/api/sources/catalog/india-research').status_code==409
    assert client.post('/api/sources/catalog/not-real').status_code==404


def test_shared_host_budget_and_adaptive_capacity_are_based_on_persisted_measurements(tmp_path,monkeypatch):
    engine=create_engine(f"sqlite:///{tmp_path/'budgets.db'}")
    Base.metadata.create_all(engine)
    sessions=sessionmaker(engine,expire_on_commit=False)
    monkeypatch.setattr(rate_limits,'SessionLocal',sessions);monkeypatch.setattr(worker,'SessionLocal',sessions)
    assert rate_limits.reserve('api.example.invalid',2)==0
    assert rate_limits.reserve('api.example.invalid',2)>0
    rate_limits.reserve('api.example.invalid',30,cooldown=True)
    assert rate_limits.reserve('api.example.invalid',1)>25
    with sessions() as db:
        assert len(list(db.scalars(select(HostBudget))))==1
        for index in range(6):db.add(CrawlRun(owner_id='synthetic',source_id=str(index),outcome='error' if index<5 else 'success',seconds=1,finished_at=datetime.now(timezone.utc).isoformat()))
        db.commit()
    monkeypatch.setattr(worker.settings,'concurrency',8)
    assert worker.adaptive_capacity(8)==4
    with sessions() as db:
        for row in db.scalars(select(CrawlRun)):row.outcome='success'
        db.commit()
    assert worker.adaptive_capacity(4)==5
    engine.dispose()


def test_streaming_backup_roundtrip_rejects_tampering_and_wrong_key():
    path=Path(__file__).parents[2]/'scripts/secure-backup.py'
    spec=importlib.util.spec_from_file_location('secure_backup',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    from cryptography.fernet import Fernet
    key=Fernet.generate_key();plain=b'synthetic encrypted database backup\n'*100000
    encrypted=io.BytesIO();module.encrypt_stream(io.BytesIO(plain),encrypted,key)
    assert plain[:100] not in encrypted.getvalue()
    restored=io.BytesIO();module.decrypt_stream(io.BytesIO(encrypted.getvalue()),restored,key)
    assert restored.getvalue()==plain
    corrupt=bytearray(encrypted.getvalue());corrupt[-1]^=1
    with pytest.raises(InvalidTag):module.decrypt_stream(io.BytesIO(corrupt),io.BytesIO(),key)
    with pytest.raises(InvalidTag):module.decrypt_stream(io.BytesIO(encrypted.getvalue()),io.BytesIO(),Fernet.generate_key())


def test_crawl_retention_only_prunes_old_operational_rows(tmp_path,monkeypatch):
    engine=create_engine(f"sqlite:///{tmp_path/'retention.db'}")
    Base.metadata.create_all(engine)
    sessions=sessionmaker(engine,expire_on_commit=False)
    monkeypatch.setattr(worker,'SessionLocal',sessions)
    monkeypatch.setattr(worker.settings,'crawl_log_retention_days',14)
    with sessions() as db:
        db.add(CrawlRun(owner_id='synthetic',source_id='old',started_at=(datetime.now(timezone.utc)-timedelta(days=30)).isoformat(),outcome='success'))
        db.add(CrawlRun(owner_id='synthetic',source_id='recent',outcome='success'))
        db.commit()
    assert worker.prune_scan_history()==1
    with sessions() as db:assert [row.source_id for row in db.scalars(select(CrawlRun))]==['recent']
    engine.dispose()


def test_additive_version_five_migration_preserves_existing_encrypted_records(stack):  # noqa: F811
    client,_=stack.register()
    with stack.db() as db:
        db.execute('DELETE FROM schema_versions WHERE version=5')
        for table in ('gmail_connections','gmail_oauth_states','outreach_settings','outreach_contacts','outreach_messages','outreach_replies','crawl_runs','host_budgets'):
            db.execute('DROP TABLE '+table)
    stack.python('from app.migrate import migrate; migrate();migrate()')
    assert client.get('/api/profile').json()['graduation_year']==2029
    assert client.get('/api/outreach').json()['contacts']==[]
    with stack.db() as db:assert [row[0] for row in db.execute('SELECT version FROM schema_versions ORDER BY version')]==[1,2,3,4,5,6,7,8]


def test_outreach_schedule_requires_timezone_and_new_sessions_support_oauth_return(stack):  # noqa: F811
    client,response=stack.register()
    assert response['user']['id']
    # Existing origin/CSRF protections still reject cross-origin mutations.
    assert client.post('/api/outreach/contacts',json={},headers={'Origin':'https://untrusted.example.invalid'}).status_code==403
    assert client.get('/api/outreach/gmail/callback?state=invalid-state-long-enough&code=synthetic').status_code in {400,503}
    from app.outreach_schemas import MessageApproval
    with pytest.raises(ValueError):MessageApproval(consent=True,preview_digest='0'*64,scheduled_at='2026-10-24T09:00:00')
    aware=datetime.now(timezone.utc)+timedelta(days=1)
    assert MessageApproval(consent=True,preview_digest='0'*64,scheduled_at=aware.isoformat()).scheduled_at
