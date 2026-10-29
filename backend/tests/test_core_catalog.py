"""Core catalog invariants; all records/keys are synthetic and isolated."""
from datetime import datetime, timezone
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, event
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Opportunity, CatalogSource, User, Source, SourceOpportunity, OpportunityArchive
from app.catalog_migrations import backfill, materialize_aliases, upgrade_schema


@pytest.fixture(params=["sqlite"] + (["postgresql"] if os.getenv("PHASE4_POSTGRES_URL") else []))
def catalog_db(tmp_path, request):
    schema = "phase4_" + uuid4().hex
    admin = None
    if request.param == "postgresql":
        from sqlalchemy import text
        admin = create_engine(os.environ["PHASE4_POSTGRES_URL"])
        with admin.begin() as conn:
            conn.execute(text('CREATE SCHEMA "' + schema + '"'))
        engine = create_engine(os.environ["PHASE4_POSTGRES_URL"], connect_args={"options":"-csearch_path=" + schema})
    else:
        engine = create_engine(f"sqlite:///{tmp_path / 'catalog.db'}")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        upgrade_schema(conn)
    yield engine, sessionmaker(engine, expire_on_commit=False)
    engine.dispose()
    if admin:
        with admin.begin() as conn:
            conn.execute(text('DROP SCHEMA "' + schema + '" CASCADE'))
        admin.dispose()


def test_additive_schema_idempotent_and_reviewed_sources(catalog_db):
    engine, sessions = catalog_db
    with engine.begin() as conn:
        upgrade_schema(conn)
    with sessions() as db:
        assert len(list(db.scalars(select(CatalogSource)))) == 6


def test_alias_read_is_joined_and_never_mutates_public_facts(catalog_db):
    engine, sessions = catalog_db
    with sessions() as db:
        facts = Opportunity(id="public", fingerprint="public", catalog_scope="public", data={"title":"Software Intern", "company":"Publisher"})
        db.add(facts); db.flush()
        alias = Opportunity(id="legacy", fingerprint="legacy", data={}, canonical_id="public")
        db.add(alias); db.commit()
    statements = []
    def count(*args):
        statements.append(args[2])
    event.listen(engine, "before_cursor_execute", count)
    try:
        with sessions() as db:
            alias = db.get(Opportunity, "legacy")
            assert alias.data["title"] == "Software Intern"
            assert len(statements) == 1
            assert db.scalar(select(Opportunity.id).where(Opportunity.id == "legacy", Opportunity.data["company"].as_string() == "Publisher")) == "legacy"
            alias.data = {"title":"Private adjustment"}
            db.commit()
            assert db.get(Opportunity, "public").data["title"] == "Software Intern"
    finally:
        event.remove(engine, "before_cursor_execute", count)


def test_legacy_projection_backfill_and_recovery_preserve_ids(catalog_db):
    engine, sessions = catalog_db
    with engine.begin() as conn:
        conn.execute(Opportunity.__table__.insert(), [{"id":"old", "fingerprint":"old", "data":{"title":"Research Intern", "deadline":"2030-01-01T12:00:00+05:30"}, "first_discovered":"2026-01-01T00:00:00+00:00"}])
    assert backfill(engine, 1) == 1
    assert backfill(engine, 1) == 0
    with sessions() as db:
        old = db.get(Opportunity, "old")
        assert old.deadline_at.replace(tzinfo=timezone.utc) == datetime(2030, 1, 1, 6, 30, tzinfo=timezone.utc)
        alias = Opportunity(id="historical-ref", fingerprint="historical-ref", data={}, canonical_id="old")
        db.add(alias);db.commit()
    assert materialize_aliases(engine, 1) == 1
    assert materialize_aliases(engine, 1) == 0
    with sessions() as db:
        assert db.get(Opportunity, "historical-ref").data["title"] == "Research Intern"
        assert db.get(Opportunity, "historical-ref").canonical_id is None


def test_batched_scope_dedup_and_private_legacy_alias(catalog_db):
    from app.catalog import ingest
    from app.services import canonical_fingerprint, job_for_user
    from app.security import digest, decrypt
    engine, sessions = catalog_db
    data = {"title":"Software Intern", "company":"Figma", "url":"https://example.invalid/job/1", "remote":True}
    with sessions() as db:
        a = Source(owner_id="owner-a", kind="greenhouse", slug="figma", company="Figma", enabled=True, permitted=True)
        b = Source(owner_id="owner-b", kind="greenhouse", slug="figma", company="Figma", enabled=True, permitted=True)
        c = Source(owner_id="owner-c", kind="feed", company="Private")
        db.add_all([a,b,c]);db.flush()
        legacy = Opportunity(id="legacy-owned-a", fingerprint=digest("owner-a:" + canonical_fingerprint(data)), data={**data,"private_note":"never publish"})
        db.add(legacy);db.flush()
        db.add(SourceOpportunity(source_id=a.id, opportunity_id=legacy.id));db.commit()
        rows, _, _, _ = ingest(db, "owner-a", a, [data], public=True)
        public_id = rows[0].id
        db.commit()
        rows, _, _, _ = ingest(db, "owner-b", b, [data, data], public=True)
        db.commit()
        assert rows[0].id == public_id
        assert "private_note" not in rows[0].data
        assert db.get(Opportunity, legacy.id).canonical_id == public_id
        assert job_for_user(db, "owner-a", legacy.id) is not None
        assert job_for_user(db, "owner-b", legacy.id) is None
        assert job_for_user(db, "owner-b", public_id) is not None
        snapshot = db.get(OpportunityArchive, legacy.id)
        assert snapshot.owner_id == "owner-a" and decrypt(snapshot.payload_encrypted)["private_note"] == "never publish"
        private, _, _, _ = ingest(db, "owner-c", c, [{**data, "title":"Private note"}], public=False)
        db.commit()
        assert private[0].id != public_id
        assert db.get(Opportunity, public_id).data["title"] == "Software Intern"
        with pytest.raises(PermissionError):
            ingest(db, "owner-c", b, [data])
        with pytest.raises(PermissionError):
            ingest(db, "owner-c", c, [data], public=True)


def test_ingestion_query_count_bounded_per_batch(catalog_db):
    from app.catalog import ingest
    engine, sessions = catalog_db
    with sessions() as db:
        source = Source(owner_id="owner", kind="feed", company="Private")
        db.add(source);db.commit()
        source_id = source.id
    statements = []
    def count(*args):
        statements.append(args[2])
    event.listen(engine, "before_cursor_execute", count)
    try:
        with sessions() as db:
            source = db.get(Source, source_id)
            rows = [{"title":"Student Intern", "url":f"https://example.invalid/{i}"} for i in range(200)]
            ingest(db, "owner", source, rows)
            db.commit()
        assert len(statements) <= 8
        assert not any("SAVEPOINT" in sql for sql in statements)
    finally:
        event.remove(engine, "before_cursor_execute", count)


def test_reviewed_source_fetch_once_for_two_subscribers(catalog_db, monkeypatch):
    import asyncio
    from app import services, discovery
    from app.schemas import Profile, Policy
    from app.security import encrypt
    _, sessions = catalog_db
    monkeypatch.setattr(services, "SessionLocal", sessions)
    calls = []
    async def fetch(source, cache):
        calls.append(source["id"])
        return {"jobs":[{"title":"Software Intern", "company":"Figma", "url":"https://example.invalid/shared", "source":"greenhouse"}], "cache":{}}
    monkeypatch.setattr(discovery, "discover", fetch)
    with sessions() as db:
        for owner in ("owner-a", "owner-b"):
            db.add(User(id=owner, email_hash=owner, email_encrypted=encrypt(owner), password_hash="synthetic",
                profile_encrypted=encrypt(Profile().model_dump()), policy_encrypted=encrypt(Policy().model_dump())))
            db.add(Source(id="source-" + owner, owner_id=owner, kind="greenhouse", slug="figma", company="Private account label", url="https://example.invalid/private-label", enabled=True, permitted=True))
        db.commit()
    asyncio.run(services.process_discovery("owner-a"))
    asyncio.run(services.process_discovery("owner-b"))
    asyncio.run(services.process_discovery("owner-a"))
    with sessions() as db:
        assert len(calls) == 1
        assert len(list(db.scalars(select(Opportunity).where(Opportunity.catalog_scope == "public")))) == 1
        assert len(list(db.scalars(select(SourceOpportunity)))) == 2
        facts = db.scalar(select(Opportunity))
        assert facts.data["company"] == "Figma"
        assert "private-label" not in str(facts.data) and "Private account" not in str(facts.data)


def test_notification_dedupe_is_per_owner_and_saved_fanout(catalog_db):
    from app.services import event as emit, notify_saved_changes
    from app.models import Notification, SavedOpportunity
    engine, sessions = catalog_db
    with sessions() as db:
        root = Opportunity(id="notify-root", fingerprint="notify-root", data={"title":"Public Intern"}, catalog_scope="public")
        db.add(root);db.flush()
        db.add(Opportunity(id="notify-alias", fingerprint="notify-alias", data={}, canonical_id=root.id))
        db.flush()
        db.add_all([SavedOpportunity(owner_id="owner-a", opportunity_id="notify-alias"), SavedOpportunity(owner_id="owner-b", opportunity_id=root.id)])
        for owner in ("owner-a", "owner-b"):
            emit(db, owner, "high_match", "Public role matches your profile", notify=True, dedupe_key="match:one-global-role")
            emit(db, owner, "high_match", "Duplicate", notify=True, dedupe_key="match:one-global-role")
        messages = {root.id:("saved_opportunity_changed", "Public deadline changed", "same-episode")}
        notify_saved_changes(db, messages)
        notify_saved_changes(db, messages)
        db.commit()
        rows = list(db.scalars(select(Notification)))
        assert len(rows) == 4
        changes = [r for r in rows if r.kind == "saved_opportunity_changed"]
        assert {(r.owner_id, r.opportunity_id) for r in changes} == {("owner-a", "notify-alias"), ("owner-b", root.id)}


def test_reused_worker_attempt_cannot_commit_or_ack(catalog_db, monkeypatch):
    import asyncio
    from datetime import timedelta
    from app import services, worker, discovery
    from app.models import Task
    from app.schemas import Policy, Profile
    from app.security import encrypt
    _, sessions = catalog_db
    monkeypatch.setattr(services, "SessionLocal", sessions)
    monkeypatch.setattr(worker, "SessionLocal", sessions)
    with sessions() as db:
        db.add(User(id="lease-owner", email_hash="lease-owner", email_encrypted=encrypt("synthetic@example.invalid"), password_hash="synthetic", profile_encrypted=encrypt(Profile().model_dump()), policy_encrypted=encrypt(Policy().model_dump())))
        db.add(Source(id="lease-source", owner_id="lease-owner", kind="feed", company="Private fixture", enabled=True, permitted=True))
        db.add(Task(id="lease-task", owner_id="lease-owner", kind="discovery", dedupe_key="lease-fixture", payload={"source_id":"lease-source"}, status="running", attempts=1, lease_owner="same-worker", lease_until=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()))
        db.commit()
    async def fetch(*args, **kwargs):
        with sessions() as db:
            db.get(Task, "lease-task").attempts = 2
            source = db.get(Source, "lease-source")
            source.scan_generation += 1
            db.commit()
        return {"jobs":[{"title":"Obsolete result", "url":"https://example.invalid/obsolete"}], "cache":{}}
    monkeypatch.setattr(discovery, "discover", fetch)
    asyncio.run(worker.execute_task({"id":"lease-task", "owner_id":"lease-owner", "kind":"discovery", "payload":{"source_id":"lease-source"}, "attempts":1}, "same-worker"))
    with sessions() as db:
        assert db.get(Task, "lease-task").status == "running"
        assert db.get(Task, "lease-task").attempts == 2
        assert list(db.scalars(select(Opportunity))) == []


def test_concurrent_overlapping_batches(catalog_db):
    from concurrent.futures import ThreadPoolExecutor
    from app.catalog import ingest
    engine, sessions = catalog_db
    if engine.dialect.name != "postgresql":
        pytest.skip("Multi-batch row-lock ordering requires PostgreSQL")
    with sessions() as db:
        for index in range(4):
            db.add(Source(id=f"batch-source-{index}", owner_id=f"batch-owner-{index}", kind="greenhouse", slug="figma", company="Figma", enabled=True, permitted=True))
        db.commit()
    def write(index):
        with sessions() as db:
            source = db.get(Source, f"batch-source-{index}")
            ingest(db, source.owner_id, source, [{"title":"Software Intern", "url":f"https://example.invalid/batch/{i}"} for i in range(index * 50, index * 50 + 250)], public=True)
            db.commit()
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(write, range(4)))
    with sessions() as db:
        assert len(list(db.scalars(select(Opportunity)))) == 400
        assert len(list(db.scalars(select(SourceOpportunity)))) == 1000


def test_cursor_scope_filters_and_ties(catalog_db):
    from app.catalog_query import cursor_page
    from app.schemas import Profile
    from app.security import encrypt
    from fastapi import HTTPException
    _, sessions = catalog_db
    with sessions() as db:
        owner = User(id="cursor-owner", email_hash="cursor-owner", email_encrypted=encrypt("synthetic@example.invalid"), password_hash="synthetic", profile_encrypted=encrypt(Profile().model_dump()), policy_encrypted=encrypt({}))
        source = Source(id="cursor-source", owner_id=owner.id, kind="feed", company="Fixture")
        db.add_all([owner, source]);db.flush()
        for index in range(7):
            row = Opportunity(id=f"cursor-{index}", fingerprint=f"cursor-{index}", first_discovered="2026-01-01T00:00:00+00:00", data={"title":"Software Intern", "company":"Straße Labs", "remote":True, "location":"Pune", "deadline":"2099-01-01" if index < 4 else None})
            db.add(row);db.flush()
            db.add(SourceOpportunity(source_id=source.id, opportunity_id=row.id))
        db.add(Opportunity(id="hidden", fingerprint="hidden", data={"title":"Private unrelated opportunity"}))
        db.commit()
        seen = []
        cursor = ""
        for _ in range(4):
            page = cursor_page(db, owner, cursor=cursor, page_size=2, company="STRASSE")
            seen.extend(x["id"] for x in page["items"])
            cursor = page["next_cursor"]
            if not cursor:
                break
        assert len(seen) == len(set(seen)) == 7 and "hidden" not in seen
        first = cursor_page(db, owner, page_size=2, sort="deadline")
        assert all(x["deadline"] for x in first["items"])
        with pytest.raises(HTTPException):
            cursor_page(db, owner, page_size=2, sort="newest", cursor=first["next_cursor"])
        other = User(id="other", profile_encrypted=encrypt(Profile().model_dump()))
        with pytest.raises(HTTPException):
            cursor_page(db, other, page_size=2, sort="deadline", cursor=first["next_cursor"])
        assert cursor_page(db, other)["items"] == []
        with pytest.raises(HTTPException):
            cursor_page(db, owner, cursor="tampered")


def test_postgresql_fulltext_index_and_filter(catalog_db):
    from app.catalog_migrations import build_indexes
    from app.catalog_query import cursor_page
    from app.schemas import Profile
    from app.security import encrypt
    from sqlalchemy import text
    engine, sessions = catalog_db
    if engine.dialect.name != "postgresql":
        pytest.skip("Full-text planner requires PostgreSQL")
    with sessions() as db:
        user = User(id="fts-owner", email_hash="fts-owner", email_encrypted=encrypt("synthetic@example.invalid"), password_hash="synthetic", profile_encrypted=encrypt(Profile().model_dump()), policy_encrypted=encrypt({}))
        source = Source(id="fts-source", owner_id=user.id, kind="feed", company="Fixture")
        db.add_all([user, source]);db.flush()
        for ident, title in [("fts-yes", "PyTorch Research Internship"), ("fts-no", "Cloud Student Program")]:
            db.add(Opportunity(id=ident, fingerprint=ident, data={"title":title}));db.flush()
            db.add(SourceOpportunity(source_id=source.id, opportunity_id=ident))
        db.commit()
        assert build_indexes(engine)["full_text"]
        assert build_indexes(engine)["full_text"]
        page = cursor_page(db, user, search="pytorch", search_mode="text")
        assert [x["id"] for x in page["items"]] == ["fts-yes"]
        assert db.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_indexes WHERE schemaname=current_schema() AND indexname='ix_catalog_fulltext')"))


def test_concurrent_public_dedup_has_one_fact_record(catalog_db):
    from concurrent.futures import ThreadPoolExecutor
    from app.catalog import ingest
    engine, sessions = catalog_db
    with sessions() as db:
        for index in range(6):
            db.add(Source(id=f"parallel-source-{index}", owner_id=f"parallel-owner-{index}", kind="greenhouse", slug="figma", company="Figma", enabled=True, permitted=True))
        db.commit()
    def write(index):
        with sessions() as db:
            source = db.get(Source, f"parallel-source-{index}")
            rows, _, _, _ = ingest(db, source.owner_id, source, [{"title":"Software Intern", "company":"Figma", "url":"https://example.invalid/parallel"} for _ in range(3)], public=True)
            db.commit()
            return rows[0].id
    with ThreadPoolExecutor(max_workers=6) as pool:
        ids = list(pool.map(write, range(6)))
    assert len(set(ids)) == 1
    with sessions() as db:
        assert len(list(db.scalars(select(SourceOpportunity)))) == 6


@pytest.mark.parametrize("legacy_version", [1, 5])
def test_frozen_historical_upgrade_preserves_encrypted_data_and_references(catalog_db, monkeypatch, legacy_version):
    from pathlib import Path
    from sqlalchemy import text, Table, MetaData, JSON, LargeBinary, Boolean, Integer
    from app import migrate as migration
    from app.models import Application, Document, SavedOpportunity
    from app.security import encrypt, encrypt_bytes, decrypt_bytes
    engine, sessions = catalog_db
    fixture = Path(__file__).parent / "fixtures" / (f"schema_v{legacy_version}_" + engine.dialect.name + ".sql")
    with engine.begin() as conn:
        Base.metadata.drop_all(conn)
        ddl = "\n".join(line for line in fixture.read_text().splitlines() if not line.lstrip().startswith("--"))
        for statement in ddl.split(";"):
            if statement.strip():
                conn.exec_driver_sql(statement)
        meta = MetaData()
        def insert(name, **values):
            table = Table(name, meta, autoload_with=conn)
            for column in table.c:
                if column.name not in values and not column.nullable:
                    values[column.name] = {} if isinstance(column.type, JSON) else b"fixture" if isinstance(column.type, LargeBinary) else False if isinstance(column.type, Boolean) else 0 if isinstance(column.type, Integer) else ""
            conn.execute(table.insert().values(**values))
        for version in range(1, legacy_version + 1):
            insert("schema_versions", version=version, applied_at="2026-01-01T00:00:00+00:00")
        encrypted = encrypt({"country":"India", "graduation_year":2029})
        document = encrypt_bytes(b"synthetic original document")
        insert("users", id="v5-user", email_hash="v5-email", email_encrypted=encrypt("synthetic@example.invalid"), profile_encrypted=encrypted, policy_encrypted=encrypt({}))
        insert("sources", id="v5-source", owner_id="v5-user", kind="feed", company="Private", cache={})
        insert("opportunities", id="v5-job", fingerprint="v5-job", data={"title":"Original Intern", "url":"https://example.invalid/original"}, first_discovered="2026-01-01T00:00:00+00:00", last_verified="2026-01-01T00:00:00+00:00")
        insert("source_opportunities", source_id="v5-source", opportunity_id="v5-job")
        if legacy_version >= 3:
            insert("saved_opportunities", owner_id="v5-user", opportunity_id="v5-job")
        insert("applications", id="v5-application", owner_id="v5-user", opportunity_id="v5-job", status="submitted", confirmation_id="synthetic-receipt")
        insert("documents", id="v5-document", owner_id="v5-user", opportunity_id="v5-job", content_encrypted=document, metadata_encrypted=encrypt({}))
    monkeypatch.setattr(migration, "engine", engine)
    migration.migrate();migration.migrate()
    assert backfill(engine) == 1
    with sessions() as db:
        assert db.get(User, "v5-user").profile_encrypted == encrypted
        assert db.get(Opportunity, "v5-job").data["title"] == "Original Intern"
        assert db.get(Application, "v5-application").opportunity_id == "v5-job"
        assert db.get(Document, "v5-document").content_encrypted == document
        assert decrypt_bytes(document) == b"synthetic original document"
        if legacy_version >= 3:
            assert db.get(SavedOpportunity, ("v5-user", "v5-job"))
        assert db.scalar(text("SELECT max(version) FROM schema_versions")) == 8
