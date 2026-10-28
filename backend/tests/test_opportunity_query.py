"""Query scaling and exact filter semantics using isolated synthetic records."""
from datetime import datetime, timedelta, timezone
from time import perf_counter

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.discovery_filters import DiscoveryCriteria
from app.matching import extract_requirements
from app.models import Opportunity, SavedOpportunity, Source, SourceOpportunity, User
from app.opportunity_query import candidate_query, query_opportunities
from app.schemas import Profile
from app.security import digest, encrypt
from app.services import job_view


@pytest.fixture
def catalog(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'catalog.sqlite3'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    profile = Profile(degree="Bachelor of Technology", skills=["Python"], verified_fields=["degree", "graduation_year", "country", "skills"]).model_dump()
    with sessions() as db:
        user = User(email_hash=digest("owner"), email_encrypted=encrypt("owner@example.invalid"), password_hash="synthetic-only", profile_encrypted=encrypt(profile), policy_encrypted=encrypt({}))
        other = User(email_hash=digest("other"), email_encrypted=encrypt("other@example.invalid"), password_hash="synthetic-only", profile_encrypted=encrypt(profile), policy_encrypted=encrypt({}))
        db.add_all([user, other]); db.flush()
        sources = [Source(owner_id=account.id, kind="html", company="Synthetic source", permitted=True, enabled=True) for account in (user, other)]
        db.add_all(sources); db.flush()
        owner_id, other_id = user.id, other.id
        source_id, private_source = sources[0].id, sources[1].id
        description = "Currently pursuing a Bachelor's degree. Graduating in 2029. Must be based in India. Python. Internship duration: 6 months."
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        records, links = [], []
        for index in range(1000):
            ident = f"opportunity-{index:04d}"
            data = {"title": "Software Intern", "company": "Synthetic small employer", "url": f"https://example.invalid/jobs/{index}",
                    "description": description, "skills": ["Python"], "requirements": extract_requirements(description),
                    "location": "Pune, India", "remote": True, "deadline": "2099-01-01T00:00:00Z", "compensation": "INR 20000 / month"}
            records.append({"id": ident, "fingerprint": digest(ident), "data": data, "first_discovered": (start + timedelta(seconds=index)).isoformat()})
            links.append({"source_id": source_id, "opportunity_id": ident})
        private = {"id":"private", "fingerprint":digest("private"), "data":records[-1]["data"]}
        db.execute(Opportunity.__table__.insert(), records)
        db.execute(Opportunity.__table__.insert(), [private])
        db.execute(SourceOpportunity.__table__.insert(), links + [{"source_id":private_source, "opportunity_id":"private"}])
        db.commit()
    yield sessions, owner_id, other_id, source_id
    engine.dispose()


def test_thousand_record_chronological_page_evaluates_and_hydrates_only_twenty(catalog):
    sessions, owner, other, _ = catalog
    evaluated, hydrated = [], []
    def counted_view(row, profile):
        evaluated.append(row.id)
        return job_view(row, profile)
    def loaded(session, row):
        if isinstance(row, Opportunity):
            hydrated.append(row.id)
    event.listen(Session, "loaded_as_persistent", loaded)
    try:
        with sessions() as db:
            user = db.get(User, owner)
            started = perf_counter()
            first = query_opportunities(db, user, page=1, page_size=20, sort="newest", kind="internship", view=counted_view)
            elapsed = perf_counter() - started
            assert first["total"] == 1000 and len(evaluated) == len(hydrated) == 20
            assert [row["id"] for row in first["items"]] == [f"opportunity-{index:04d}" for index in range(999, 979, -1)]
            assert elapsed < 10  # Broad ceiling catches accidentally repeated scoring.
            second = query_opportunities(db, user, page=2, page_size=20, sort="newest", view=counted_view)
            assert not {row["id"] for row in first["items"]} & {row["id"] for row in second["items"]}
            assert len(evaluated) == len(hydrated) == 40
            assert query_opportunities(db, db.get(User, other), page=1, sort="newest")["total"] == 1
    finally:
        event.remove(Session, "loaded_as_persistent", loaded)


def test_raw_filters_keep_strict_disclosed_facts_and_timezone_semantics(catalog):
    sessions, owner, _, _ = catalog
    with sessions() as db:
        for ident, changes in [
            ("opportunity-0999", {"deadline":"2000-01-01T00:00:00+05:30"}),
            ("opportunity-0998", {"active":False}),
            ("opportunity-0997", {"requirements":{}, "compensation":None}),
            ("opportunity-0996", {"location":"Remote - United States"}),
        ]:
            row = db.get(Opportunity, ident); row.data = {**row.data, **changes}
        db.commit()
        user = db.get(User, owner)
        options = {"sort":"newest", "region":"local", "location":"Pune", "remote":"true", "paid":"true", "criteria":DiscoveryCriteria(graduation_year=2029, degree_level="undergraduate", duration_min=3, stipend_min=15000)}
        result = query_opportunities(db, user, page=1, page_size=20, **options)
        all_rows = query_opportunities(db, user, **options)
        assert result["total"] == len(all_rows) == 996
        assert [row["id"] for row in result["items"]] == [row["id"] for row in all_rows[:20]]
        assert query_opportunities(db, user, page=1, sort="deadline", include_closed=True, deadline_before="2021-01-01")["total"] == 1
        with pytest.raises(Exception, match="Deadline filter"):
            query_opportunities(db, user, page=1, sort="newest", deadline_before="invalid")


def test_score_and_eligibility_pages_preserve_full_evaluation_results(catalog):
    sessions, owner, _, _ = catalog
    with sessions() as db:
        row = db.get(Opportunity, "opportunity-0999")
        row.data = {**row.data, "description":"Graduating in 2027 only.", "requirements":{"graduation_years":[2027]}}
        db.commit()
        user = db.get(User, owner)
        for sort in ("score", "newest", "deadline"):
            options = {"sort":sort, "recommended":True, "min_score":50}
            all_rows = query_opportunities(db, user, **options)
            result = query_opportunities(db, user, page=2, page_size=20, **options)
            assert result["total"] == len(all_rows) == 999
            assert [item["id"] for item in result["items"]] == [item["id"] for item in all_rows[20:40]]
        rejected = query_opportunities(db, user, page=1, sort="newest", eligibility="ineligible")
        assert rejected["total"] == 1 and rejected["items"][0]["id"] == "opportunity-0999"


def test_casefold_search_literal_wildcards_cross_fields_and_strict_remote(catalog):
    sessions, owner, _, _ = catalog
    with sessions() as db:
        updates = [
            ("opportunity-0000", {"title":"Student Developer", "company":"Straße Labs"}),
            ("opportunity-0001", {"title":"Software", "company":"Team", "remote":1}),
            ("opportunity-0002", {"company":"100%_Local"}),
            ("opportunity-0003", {"remote":"sometimes"}),
        ]
        for ident, changes in updates:
            row = db.get(Opportunity, ident); row.data = {**row.data, **changes}
        db.commit()
        user = db.get(User, owner)
        assert query_opportunities(db, user, page=1, sort="newest", company="STRASSE")["total"] == 1
        assert query_opportunities(db, user, page=1, sort="newest", search="STRASSE")["total"] == 1
        assert query_opportunities(db, user, page=1, sort="newest", search="Software Team")["total"] == 1
        assert query_opportunities(db, user, page=1, sort="newest", company="%_")["total"] == 1
        assert query_opportunities(db, user, page=1, sort="newest", search="Software Team", remote="true")["total"] == 0


def test_search_distinguishes_missing_fields_from_explicit_null(catalog):
    sessions, owner, _, _ = catalog
    with sessions() as db:
        missing = db.get(Opportunity, "opportunity-0000")
        missing.data = {"title":"Software", "description":"Intern", "location":"Pune"}
        null = db.get(Opportunity, "opportunity-0001")
        null.data = {"title":"Software", "company":None, "description":"Intern", "location":"Pune"}
        db.commit()
        user = db.get(User, owner)
        assert query_opportunities(db, user, page=1, sort="newest", search="Software  Intern")["total"] == 1
        assert query_opportunities(db, user, page=1, sort="newest", search="Software None Intern")["total"] == 1


def test_postgresql_prefilters_never_cast_untrusted_remote_values_to_boolean():
    class Bind:
        dialect = postgresql.dialect()
    class DB:
        def get_bind(self):
            return Bind()
    compiled = str(candidate_query(DB(), "synthetic-owner", kind="internship", remote="true", search="STRASSE").compile(dialect=postgresql.dialect())).upper()
    assert "BOOLEAN" not in compiled
    assert "VARCHAR" in compiled and "JSON_TYPEOF" in compiled


def test_saved_orphans_remain_visible_and_status_decoration_is_owner_scoped(catalog):
    sessions, owner, other, source_id = catalog
    with sessions() as db:
        db.add(SavedOpportunity(owner_id=owner, opportunity_id="opportunity-0000")); db.commit()
        link = db.get(SourceOpportunity, (source_id, "opportunity-0000")); db.delete(link); db.commit()
        user = db.get(User, owner)
        assert query_opportunities(db, user, page=1, sort="newest")["total"] == 999
        saved = query_opportunities(db, user, page=1, sort="newest", saved=True)
        assert saved["total"] == 1 and saved["items"][0]["saved"] is True
        assert query_opportunities(db, db.get(User, other), page=1, sort="newest", saved=True)["total"] == 0
        assert db.scalar(select(Opportunity.id).where(Opportunity.id == "opportunity-0000"))
