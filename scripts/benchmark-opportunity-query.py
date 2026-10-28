"""Measured local query benchmark. Synthetic records, no network or user data."""
import json
import os
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter

from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix="internpilot-query-benchmark-") as directory:
        os.environ.update(DATA_DIR=directory, DATABASE_URL=f"sqlite:///{Path(directory) / 'benchmark.db'}",
                          ENCRYPTION_KEY=Fernet.generate_key().decode(), REDIS_URL="", LLM_PROVIDER="disabled")
        sys.path.insert(0, str(ROOT / "backend"))
        from app.database import Base, SessionLocal, engine
        from app.matching import extract_requirements
        from app.models import Opportunity, Source, SourceOpportunity, User
        from app.opportunity_query import query_opportunities
        from app.schemas import Profile
        from app.security import digest, encrypt
        from app.services import job_view
        from sqlalchemy import event, select
        from sqlalchemy.orm import Session

        Base.metadata.create_all(engine)
        profile = Profile(degree="B.Tech", verified_fields=["degree", "country", "graduation_year"]).model_dump()
        description = "Currently pursuing a Bachelor's degree, graduating in 2029. Must be based in India. Python."
        requirements = extract_requirements(description)
        count, page_size = 10000, 20
        with SessionLocal() as db:
            user = User(email_hash=digest("synthetic query benchmark"), email_encrypted=encrypt("synthetic@example.invalid"),
                        password_hash="synthetic-only-unused", profile_encrypted=encrypt(profile), policy_encrypted=encrypt({}))
            db.add(user); db.flush()
            owner_id = user.id
            source = Source(owner_id=owner_id, kind="html", company="SYNTHETIC query benchmark", enabled=False, permitted=False)
            db.add(source); db.flush()
            start = datetime(2026, 1, 1, tzinfo=UTC)
            for batch_start in range(0, count, 500):
                rows, links = [], []
                for index in range(batch_start, min(count, batch_start + 500)):
                    ident = f"synthetic-{index:05d}"
                    rows.append({"id": ident, "fingerprint": digest(ident), "first_discovered": (start + timedelta(seconds=index)).isoformat(),
                                 "data": {"title": "SYNTHETIC Software Intern", "company": "SYNTHETIC Employer", "location": "Pune, India",
                                          "url": f"https://synthetic.example.invalid/jobs/{index}", "description": description,
                                          "requirements": requirements, "remote": True, "active": True, "deadline": "2099-01-01T00:00:00Z"}})
                    links.append({"source_id": source.id, "opportunity_id": ident})
                db.execute(Opportunity.__table__.insert(), rows)
                db.execute(SourceOpportunity.__table__.insert(), links)
            db.commit()
        evaluations, hydrations = [], []
        def evaluate(row, candidate):
            evaluations.append(row.id)
            return job_view(row, candidate)
        def loaded(session, row):
            if isinstance(row, Opportunity):
                hydrations.append(row.id)
        event.listen(Session, "loaded_as_persistent", loaded)
        try:
            with SessionLocal() as db:
                user = db.scalar(select(User).where(User.id == owner_id))
                started = perf_counter()
                result = query_opportunities(db, user, page=1, page_size=page_size, sort="newest", kind="internship", view=evaluate)
                elapsed = perf_counter() - started
                assert result["total"] == count and len(result["items"]) == page_size
                assert len(evaluations) == len(hydrations) == page_size
        finally:
            event.remove(Session, "loaded_as_persistent", loaded)
            engine.dispose()
        report = {"at": datetime.now(UTC).isoformat(), "database": "SQLite", "synthetic_only": True,
                  "records": count, "page_size": page_size, "matching_evaluations": len(evaluations),
                  "orm_hydrations": len(hydrations), "query_seconds": round(elapsed, 6),
                  "candidate_batch_size": 200, "exact_totals_scan_candidates": True,
                  "http_requests": 0, "browser_launches": 0,
                  "note": "One local newest-page measurement, not cloud throughput, indexed-only pagination or a best-match benchmark."}
        (ROOT / "artifacts" / "warm-query-benchmark.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
