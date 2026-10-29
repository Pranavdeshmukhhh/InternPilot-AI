"""Disposable PostgreSQL microbenchmark, never production throughput evidence.

Requires PHASE4_POSTGRES_URL pointing to a non-superuser-owned local database
whose database comment is exactly 'InternPilot Phase4 synthetic benchmark only'.
Only a random per-run schema is created/dropped. No network discovery or sends.
"""
import argparse
import json
import os
import platform
import statistics
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=int, choices=[10000, 100000, 1000000], default=10000)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--confirm-synthetic-only", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.confirm_synthetic_only or args.repeats < 3:
        parser.error("Confirm synthetic isolation and use at least three repetitions")
    from cryptography.fernet import Fernet
    from sqlalchemy import create_engine, event, func, insert, select, text
    from sqlalchemy.engine import make_url
    url = os.getenv("PHASE4_POSTGRES_URL", "")
    parsed = make_url(url) if url else None
    if not parsed or parsed.host not in {"127.0.0.1", "localhost"} or not parsed.database.startswith("phase4_"):
        parser.error("Explicit PHASE4_POSTGRES_URL must name a disposable local phase4_ database")
    import shutil
    if shutil.disk_usage(ROOT).free < args.records * 4096:
        parser.error("Insufficient workspace disk headroom; use a larger isolated lab")
    admin = create_engine(url)
    schema = "phase4_perf_" + uuid4().hex[:16]
    with admin.begin() as conn:
        marker = conn.scalar(text("SELECT shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()"))
        if marker != "InternPilot Phase4 synthetic benchmark only" or conn.scalar(text("SELECT rolsuper FROM pg_roles WHERE rolname=current_user")):
            parser.error("Database marker missing or role is superuser; refusing benchmark")
        conn.exec_driver_sql('CREATE SCHEMA "' + schema + '"')
    engine = create_engine(url, connect_args={"options":"-csearch_path=" + schema}, pool_size=5, max_overflow=0)
    try:
        with tempfile.TemporaryDirectory(prefix="phase4-benchmark-") as directory:
            os.environ.update(DATA_DIR=directory, DATABASE_URL="sqlite:///:memory:", ENCRYPTION_KEY=Fernet.generate_key().decode(),
                ENVIRONMENT="development", REDIS_URL="", LLM_PROVIDER="disabled", LLM_API_KEY="", BRAVE_SEARCH_API_KEY="",
                GMAIL_CLIENT_ID="", GMAIL_CLIENT_SECRET="", TELEGRAM_BOT_TOKEN="", SMTP_PASSWORD="", TWILIO_AUTH_TOKEN="")
            sys.path.insert(0, str(ROOT / "backend"))
            import heapq

            from app.catalog_migrations import build_indexes
            from app.catalog_projection import projection
            from app.catalog_query import cursor_page, indexed_query
            from app.database import Base
            from app.matching import extract_requirements
            from app.models import Opportunity, Source, SourceOpportunity, User
            from app.opportunity_query import (
                _decorate,
                _raw_matches,
                _sort_key,
                query_opportunities,
            )
            from app.schemas import Profile
            from app.security import decrypt, digest, encrypt
            from app.services import job_view
            from sqlalchemy.orm import sessionmaker
            Base.metadata.create_all(engine)
            sessions = sessionmaker(engine, expire_on_commit=False)
            profile = Profile(degree="B.Tech", skills=["Python"], verified_fields=["degree", "country", "graduation_year", "skills"]).model_dump()
            owner, source_id = "synthetic-benchmark-owner", "synthetic-benchmark-source"
            description = "SYNTHETIC. Currently pursuing a Bachelor's degree, graduating 2029. Must be based in India. Python required. Internship duration: 6 months."
            req = extract_requirements(description)
            start = datetime.now(UTC) - timedelta(seconds=args.records + 3600)
            with sessions() as db:
                db.add(User(id=owner, email_hash=digest(owner), email_encrypted=encrypt("synthetic@example.invalid"), password_hash="synthetic-only-unused", profile_encrypted=encrypt(profile), policy_encrypted=encrypt({})))
                db.add(Source(id=source_id, owner_id=owner, kind="feed", company="SYNTHETIC only", enabled=False, permitted=False))
                db.commit()
            for offset in range(0, args.records, 500):
                facts, links = [], []
                for index in range(offset, min(args.records, offset + 500)):
                    ident = f"synthetic-{index:08d}"
                    discovered = (start + timedelta(seconds=index)).isoformat()
                    data = {"title":"SYNTHETIC Software Intern" if index % 10 < 8 else "SYNTHETIC Student Hackathon",
                        "company":"SYNTHETIC Rare Labs" if index % 1000 == 0 else "SYNTHETIC Employer",
                        "location":"Pune, India" if index % 3 else "Nagpur, India", "remote":index % 2 == 0,
                        "description":description + (" PyTorch." if index % 100 == 0 else ""), "requirements":req,
                        "skills":["Python"], "url":f"https://synthetic.example.invalid/jobs/{index}", "deadline":"2099-01-01T00:00:00Z",
                        "opportunity_type":"internship" if index % 10 < 8 else "hackathon"}
                    facts.append({"id":ident, "fingerprint":digest(ident), "data":data, "catalog_scope":"public",
                        "first_discovered":discovered, "last_verified":discovered, **projection(data, discovered)})
                    links.append({"source_id":source_id, "opportunity_id":ident})
                with engine.begin() as conn:
                    conn.execute(insert(Opportunity.__table__), facts)
                    conn.execute(insert(SourceOpportunity.__table__), links)
            build_indexes(engine)
            with engine.begin() as conn:
                conn.exec_driver_sql("ANALYZE")

            def legacy(db, user):
                # Frozen v5 chronological algorithm: exact totals + Python heap
                # over every candidate, then only selected page hydration/scoring.
                at = datetime.now(UTC)
                candidate_profile = decrypt(user.profile_encrypted)
                # v5 read the physical JSON column, before canonical alias resolution.
                raw = Opportunity.__table__.c.data
                ids = select(SourceOpportunity.opportunity_id).join(Source, Source.id == SourceOpportunity.source_id).where(Source.owner_id == user.id)
                q = select(Opportunity.id, raw, Opportunity.first_discovered).where(Opportunity.id.in_(ids), func.coalesce(raw["opportunity_type"].as_string(), "internship") == "internship").order_by(Opportunity.id)
                examined = 0
                def candidates():
                    nonlocal examined
                    for ident, payload, discovered in db.execute(q.execution_options(yield_per=200)):
                        examined += 1
                        if _raw_matches(payload, candidate_profile, {"kind":"internship"}, None, at):
                            yield ident, _sort_key(payload, discovered, "newest")
                picked = [i for i, _ in heapq.nlargest(20, candidates(), key=lambda r:r[1])]
                hydrated = {row.id:row for row in db.scalars(select(Opportunity).where(Opportunity.id.in_(picked)))}
                views = _decorate(db, user.id, [job_view(hydrated[i], profile) for i in picked])
                return [row["id"] for row in views], examined

            statement_count = [0]
            def count(*_):
                statement_count[0] += 1
            event.listen(engine, "before_cursor_execute", count)
            paths = {
                "legacy_python_exact_total":lambda db,u:legacy(db,u),
                "v1_indexed_exact_total":lambda db,u:([r["id"] for r in query_opportunities(db,u,page=1,page_size=20,sort="newest",kind="internship")["items"]],0),
                "v2_cursor_without_total":lambda db,u:([r["id"] for r in cursor_page(db,u,page_size=20,kind="internship")["items"]],0),
            }
            report = {"at":datetime.now(UTC).isoformat(), "synthetic_only":True, "database":"PostgreSQL",
                "records":args.records, "page_size":20, "repeats":args.repeats, "platform":platform.platform(),
                "cpu_count":os.cpu_count(), "network":"local PostgreSQL; no HTTP load/TLS", "external_requests":0,
                "note":"Warm single-client same-schema algorithm comparison. Not a concurrency, cold-cache, cloud, or 1M mixed-workload certification.", "paths":{}}
            report["resource_limits"] = {name:Path(path).read_text().strip() if Path(path).exists() else "unavailable"
                for name,path in [("cpu_max","/sys/fs/cgroup/cpu.max"),("memory_max","/sys/fs/cgroup/memory.max")]}
            expected = None
            for name, run in paths.items():
                samples, counts = [], []
                examined = 0
                for iteration in range(args.repeats + 1):
                    with sessions() as db:
                        user = db.get(User, owner)
                        statement_count[0] = 0
                        t = perf_counter(); ids, examined = run(db,user);elapsed = perf_counter()-t
                        if expected is None: expected = ids
                        assert ids == expected, name
                        if iteration:
                            samples.append(elapsed);counts.append(statement_count[0])
                report["paths"][name] = {"seconds":samples, "median_seconds":statistics.median(samples), "sql_statements":counts,
                    "python_candidates_examined":examined, "page_ids_match":True}
            plans = {}
            for mode, query in [("fts", indexed_query(owner, search="pytorch", search_mode="text")), ("company_before_trigram", indexed_query(owner, company="rare"))]:
                with engine.connect() as conn:
                    compiled = str(query.limit(20).compile(engine, compile_kwargs={"literal_binds":True}))
                    plans[mode] = conn.exec_driver_sql("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + compiled).scalar()
            build_indexes(engine, trigram=True)
            with engine.connect() as conn:
                compiled = str(indexed_query(owner, company="rare").limit(20).compile(engine, compile_kwargs={"literal_binds":True}))
                plans["company_after_trigram"] = conn.exec_driver_sql("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + compiled).scalar()
                report["postgres_version"] = conn.scalar(text("SHOW server_version"))
                report["opportunity_relation_bytes"] = conn.scalar(text("SELECT pg_total_relation_size('opportunities')"))
            report["plans"] = plans
            report["speedup_v1_median"] = report["paths"]["legacy_python_exact_total"]["median_seconds"] / report["paths"]["v1_indexed_exact_total"]["median_seconds"]
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps({"records":args.records,"paths":{k:round(v["median_seconds"],6) for k,v in report["paths"].items()},"speedup_v1_median":round(report["speedup_v1_median"],2),"report":str(args.output)}))
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.exec_driver_sql('DROP SCHEMA "' + schema + '" CASCADE')
        admin.dispose()


if __name__ == "__main__":
    main()
