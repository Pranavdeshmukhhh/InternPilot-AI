"""Isolated PostgreSQL + actual HTTP load; no discovery/network side effects.

PHASE7_POSTGRES_URL must name a local, non-superuser-owned phase4_/phase7_
database with the documented synthetic-only database comment. Each run creates
and drops one random schema. No existing tables/data are used. Requires Linux
for /proc sampling; other systems report unavailable resource metrics.
"""
import argparse
import asyncio
import hashlib
import json
import math
import os
import platform
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter, defaultdict
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def percentile(values, p):
    values = sorted(values)
    return values[max(0, math.ceil(len(values) * p) - 1)] if values else None


def summary(values):
    return {"samples": len(values), **{name: percentile(values, p) for name, p in [("p50", .5), ("p95", .95), ("p99", .99)]}}


def server(port):
    """Instrumentation is confined to this local fixture server, never app code."""
    import uvicorn
    from app.database import engine
    from app.main import app
    from sqlalchemy import event
    scope = ContextVar("lab_sql", default=None)
    stats = defaultdict(lambda: {"calls": 0, "seconds": 0.0})
    lock = threading.Lock()

    @event.listens_for(engine, "before_cursor_execute")
    def before(conn, cursor, statement, parameters, context, many):
        context.lab_started = time.perf_counter()

    @event.listens_for(engine, "after_cursor_execute")
    def after(conn, cursor, statement, parameters, context, many):
        elapsed = time.perf_counter() - context.lab_started
        key = hashlib.sha256(statement.encode()).hexdigest()[:12]
        with lock:
            stats[key]["calls"] += 1
            stats[key]["seconds"] += elapsed
            stats[key]["statement"] = " ".join(statement.split())[:2000]
        current = scope.get()
        if current is not None:
            current["queries"] += 1
            current["sql_seconds"] += elapsed

    @app.middleware("http")
    async def measured(request, call_next):
        current = {"queries": 0, "sql_seconds": 0.0}
        token = scope.set(current)
        try:
            response = await call_next(request)
            response.headers["X-Lab-Queries"] = str(current["queries"])
            response.headers["X-Lab-SQL-Seconds"] = str(current["sql_seconds"])
            return response
        finally:
            scope.reset(token)

    @app.get("/_synthetic_lab/metrics", include_in_schema=False)
    def metrics():
        with lock:
            return {"statements": dict(stats)}

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="error")


class Sampler:
    def __init__(self, pids):
        self.pids, self.rows, self.stop = set(pids), [], threading.Event()

    def sample(self):
        # Includes descendants. RSS sum double-counts shared memory; report that.
        processes = {}
        for path in Path("/proc").glob("[0-9]*/stat"):
            try:
                fields = path.read_text().rsplit(")", 1)[1].split()
                processes[int(path.parent.name)] = (int(fields[1]), int(fields[11]) + int(fields[12]), int(fields[21]) * os.sysconf("SC_PAGE_SIZE"))
            except (OSError, ValueError, IndexError):
                continue
        included = set(self.pids)
        for _ in range(8):
            included.update(pid for pid, (ppid, _, _) in processes.items() if ppid in included)
        rows = [row for pid, row in processes.items() if pid in included]
        self.rows.append({"at": time.monotonic(), "rss_sum_bytes": sum(r[2] for r in rows), "cpu_ticks": sum(r[1] for r in rows)})

    def run(self):
        while not self.stop.is_set():
            self.sample()
            self.stop.wait(.25)

    def finish(self):
        self.stop.set()
        if not self.rows:
            return {"available": False}
        first, last = self.rows[0], self.rows[-1]
        wall = last["at"] - first["at"]
        cpu = (last["cpu_ticks"] - first["cpu_ticks"]) / os.sysconf("SC_CLK_TCK")
        return {"available": True, "interval_seconds": wall, "cpu_seconds": cpu,
            "mean_cpu_cores": cpu / wall if wall else None,
            "peak_rss_sum_bytes": max(r["rss_sum_bytes"] for r in self.rows),
            "note": "Sampled process-tree RSS sum double-counts shared pages. CPU includes fixture API/PG processes only; not whole-host utilization."}


async def load(origin, accounts, concurrency, seconds):
    import httpx
    results, failures, sql_counts, sql_seconds = defaultdict(list), Counter(), defaultdict(list), defaultdict(list)
    started = time.perf_counter()
    deadline = started + seconds

    async def client(index):
        account = accounts[index % len(accounts)]
        async with httpx.AsyncClient(base_url=origin, trust_env=False, timeout=30,
            cookies={"internpilot_session": account["token"]}, headers={"X-CSRF-Token": account["csrf"]}) as http:
            n = index
            while time.perf_counter() < deadline:
                kind = n % 10
                if kind < 4:
                    name, path, params = "newest", "/api/v2/opportunities", {"kind": "internship"}
                elif kind < 6:
                    name, path, params = "fts", "/api/v2/opportunities", {"search": "pytorch", "search_mode": "text"}
                elif kind == 6:
                    name, path, params = "company_substring", "/api/v2/opportunities", {"company": "rare"}
                elif kind == 7:
                    name, path, params = "deadline", "/api/v2/opportunities", {"sort": "deadline"}
                elif kind == 8:
                    name, path, params = "profile", "/api/profile", {}
                else:
                    name, path, params = "save_write", "/api/saved/synthetic-" + str(account["index"]).zfill(8), {}
                t = time.perf_counter()
                try:
                    response = await (http.post(path) if name == "save_write" else http.get(path, params=params))
                    if response.status_code not in {200, 204}:
                        failures[str(response.status_code)] += 1
                    elif path == "/api/v2/opportunities":
                        data = response.json()
                        assert len(data["items"]) <= 20 and "next_cursor" in data
                    sql_counts[name].append(int(response.headers.get("X-Lab-Queries", 0)))
                    sql_seconds[name].append(float(response.headers.get("X-Lab-SQL-Seconds", 0)))
                except Exception as exc:  # noqa: BLE001 -- record unknown fixture failures in the error rate.
                    failures[type(exc).__name__] += 1
                results[name].append(time.perf_counter() - t)
                n += 1
                # A closed workload, 50ms think time, not an arrival-rate SLO.
                await asyncio.sleep(.05)
    await asyncio.gather(*(client(i) for i in range(concurrency)))
    elapsed = time.perf_counter() - started
    all_values = [v for values in results.values() for v in values]
    return {"concurrency": concurrency, "think_seconds": .05, "requested_seconds": seconds,
        "elapsed_seconds": elapsed, "requests": len(all_values), "rps": len(all_values) / elapsed,
        "failures": dict(failures), "error_rate": sum(failures.values()) / len(all_values) if all_values else None,
        "latency_seconds": summary(all_values), "endpoints": {name: {"latency_seconds": summary(values),
            "sql_statement_count": summary(sql_counts[name]), "sql_seconds": summary(sql_seconds[name])} for name, values in results.items()}}


def queue_probe(sessions, count):
    from concurrent.futures import ThreadPoolExecutor

    from app.models import Task, now
    from app.services import enqueue
    from app.worker import claim_task, recover_expired
    from sqlalchemy import func, select, update
    started = time.perf_counter()
    with sessions() as db:
        for i in range(count):
            enqueue(db, f"synthetic-user-{i % 20:02d}", "discovery", {"source_id": f"fixture-{i}"}, f"lab:{i}")
        db.commit()
    enqueued = time.perf_counter() - started
    # Persist a dead worker's lease; no external work has begun.
    interrupted = claim_task("synthetic-dead-worker")
    with sessions() as db:
        db.execute(update(Task).where(Task.id == interrupted["id"]).values(lease_until="2000-01-01T00:00:00+00:00"));db.commit()
    recovered = recover_expired()
    seen, lags, durations = [], [], []
    lock = threading.Lock()
    start = time.perf_counter()

    def consume(index):
        while True:
            t = time.perf_counter()
            task = claim_task(f"synthetic-worker-{index}")
            if not task:
                return
            with sessions() as db:
                row = db.get(Task, task["id"])
                lag = (datetime.now(UTC) - datetime.fromisoformat(row.created_at)).total_seconds()
                row.status, row.lease_owner, row.lease_until, row.updated_at = "completed", None, None, now()
                db.commit()
            with lock:
                seen.append(task["id"]);lags.append(lag);durations.append(time.perf_counter() - t)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(consume, range(4)))
    elapsed = time.perf_counter() - start
    assert len(seen) == count == len(set(seen)) and recovered == 1
    with sessions() as db:
        depth = db.scalar(select(func.count()).select_from(Task).where(Task.status.in_(["queued", "running"])))
    return {"synthetic_tasks": count, "workers": 4, "enqueue_seconds": enqueued, "processing_seconds": elapsed,
        "claims_per_second": count / elapsed, "claim_complete_seconds": summary(durations),
        "lag_seconds": summary(lags), "peak_queued": count, "final_depth": depth,
        "interrupted_leases_recovered": recovered, "unique_completions": len(set(seen)),
        "note": "Durable queue claims/completions only; no crawling, provider calls, documents or messages executed."}


def compare_catalog(sessions, account):
    """Same-schema alternating warm trials against the inspected Phase 5 source.

    Fixed trusted local commit, never downloaded or user-supplied executable code.
    A source archive without this commit reports the comparison unavailable.
    """
    import cProfile
    import pstats
    from types import ModuleType

    from app import catalog_query
    from app.models import User
    baseline = subprocess.run(["git", "show", "eedcf4c:backend/app/catalog_query.py"], cwd=ROOT, capture_output=True, text=True, check=False)
    if baseline.returncode:
        return {"available": False, "reason": "Fixed baseline commit eedcf4c is absent from this source archive"}
    module = ModuleType("app._trusted_phase5_catalog")
    module.__package__ = "app"
    exec(compile(baseline.stdout, "trusted-phase5-catalog.py", "exec"), module.__dict__)  # noqa: S102 -- fixed inspected local commit, not supplied code.
    timings = defaultdict(list)
    expected = None
    for iteration in range(8):
        paths = [("phase5", module.cursor_page), ("current", catalog_query.cursor_page)]
        if iteration % 2:
            paths.reverse()
        for name, query in paths:
            with sessions() as db:
                user = db.get(User, account["id"])
                t = time.perf_counter()
                result = query(db, user, kind="internship")
                elapsed = time.perf_counter() - t
                ids = [r["id"] for r in result["items"]]
                if expected is None:
                    expected = ids
                assert ids == expected
                if iteration:
                    timings[name].append(elapsed)
    profiler = cProfile.Profile()
    with sessions() as db:
        user = db.get(User, account["id"])
        profiler.enable();catalog_query.cursor_page(db, user, kind="internship");profiler.disable()
    entries = []
    for (file, line, function), (primitive, calls, own, cumulative, callers) in pstats.Stats(profiler).stats.items():
        entries.append({"file": Path(file).name, "line": line, "function": function, "calls": calls, "own_seconds": own, "cumulative_seconds": cumulative})
    return {"available": True, "baseline_commit": "eedcf4c", "same_page_ids": True,
        "note": "Seven alternating warm single-client samples, including authorization, scoring and decoration. Not HTTP concurrency.",
        "paths": {name: summary(values) for name, values in timings.items()},
        "profile_top_cumulative": sorted(entries, key=lambda r: r["cumulative_seconds"], reverse=True)[:20]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=int, choices=[10000, 100000, 1000000], default=10000)
    parser.add_argument("--concurrency", type=int, choices=[1, 10, 25, 50], default=10)
    parser.add_argument("--seconds", type=int, default=20)
    parser.add_argument("--queue-tasks", type=int, default=200)
    parser.add_argument("--pg-data-dir", type=Path, required=True, help="Disposable local PostgreSQL directory, for space guards/resource sampling")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--confirm-synthetic-only", action="store_true")
    args = parser.parse_args()
    if not args.confirm_synthetic_only or not 10 <= args.seconds <= 300 or not 20 <= args.queue_tasks <= 1000:
        parser.error("Confirm isolation; duration 10–300s and queue 20–1000")
    from cryptography.fernet import Fernet
    from sqlalchemy import create_engine, insert, text
    from sqlalchemy.engine import make_url
    url = os.getenv("PHASE7_POSTGRES_URL", "")
    parsed = make_url(url) if url else None
    if not parsed or parsed.host not in {"localhost", "127.0.0.1"} or not (parsed.database or "").startswith(("phase4_", "phase7_")):
        parser.error("Set PHASE7_POSTGRES_URL to a disposable local phase4_/phase7_ database")
    if shutil.disk_usage(args.pg_data_dir).free < args.records * 3072 + 150 * 1024 * 1024:
        parser.error("Insufficient PostgreSQL data disk headroom; scenario not executed")
    admin = create_engine(url)
    schema = "phase7_lab_" + uuid4().hex[:12]
    with admin.begin() as conn:
        marker = conn.scalar(text("SELECT shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()"))
        if marker not in {"InternPilot Phase4 synthetic benchmark only", "InternPilot Phase7 synthetic benchmark only"} or conn.scalar(text("SELECT rolsuper FROM pg_roles WHERE rolname=current_user")):
            parser.error("Missing synthetic database marker or non-superuser role")
        conn.exec_driver_sql('CREATE SCHEMA "' + schema + '"')
    process = None
    try:
      with tempfile.TemporaryDirectory(prefix="internpilot-phase7-") as directory:
        scoped = parsed.update_query_dict({"options": "-csearch_path=" + schema + " -capplication_name=internpilot-synthetic-lab"})
        os.environ.update(DATA_DIR=directory, DATABASE_URL=scoped.render_as_string(hide_password=False),
            ENCRYPTION_KEY=Fernet.generate_key().decode(), ENCRYPTION_SECRET="", ENVIRONMENT="development",
            REDIS_URL="", DATABASE_SSLMODE="", TEST_MODE="false", COOKIE_SECURE="false", PUBLIC_ORIGIN="",
            WORKER_HEARTBEAT_FILE="", WORKER_KINDS="discovery", DB_POOL_SIZE="5", DB_MAX_OVERFLOW="2",
            ALLOW_REGISTRATION="false", REGISTRATION_TOKEN="", DISTRIBUTED_RATE_LIMITS="true")
        for key in ["LLM_API_KEY", "LLM_PROVIDER", "BRAVE_SEARCH_API_KEY", "GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REDIRECT_URI", "SMTP_HOST", "SMTP_PASSWORD", "TELEGRAM_BOT_TOKEN", "TWILIO_AUTH_TOKEN"]:
            os.environ[key] = "disabled" if key == "LLM_PROVIDER" else ""
        sys.path.insert(0, str(ROOT / "backend"))
        from app.catalog_migrations import build_indexes
        from app.database import SessionLocal, engine
        from app.migrate import migrate
        from app.models import LoginSession, Opportunity, Source, User
        from app.schemas import Policy, Profile
        from app.security import digest, encrypt
        migrate()
        accounts = []
        for i in range(20):
            accounts.append({"id": f"synthetic-user-{i:02d}", "index": i, "token": secrets.token_urlsafe(32), "csrf": secrets.token_urlsafe(32)})
        profile = Profile(degree="B.Tech", skills=["Python"], verified_fields=["degree", "country", "graduation_year", "skills"]).model_dump()
        with engine.begin() as conn:
            conn.execute(insert(User.__table__), [{"id": a["id"], "email_hash": digest(a["id"]), "email_encrypted": encrypt(a["id"] + "@example.invalid"),
                "password_hash": "unused-synthetic", "profile_encrypted": encrypt(profile), "policy_encrypted": encrypt(Policy().model_dump()), "last_seen_at": datetime.now(UTC).isoformat()} for a in accounts])
            conn.execute(insert(LoginSession.__table__), [{"token_hash": digest(a["token"]), "user_id": a["id"], "csrf_token": a["csrf"], "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat()} for a in accounts])
            conn.execute(insert(Source.__table__), [{"id": f"synthetic-source-{i:04d}", "owner_id": accounts[i % 20]["id"], "kind": "test", "company": "SYNTHETIC disabled source", "enabled": False, "permitted": False} for i in range(1000)])
        seed_started = time.perf_counter()
        # Bounded SQL-generated synthetic facts. Every user owns 50 of 1,000
        # disabled sources, and sees approximately 1/20 of the catalog.
        for offset in range(0, args.records, 5000):
            if shutil.disk_usage(args.pg_data_dir).free < 128 * 1024 * 1024:
                raise RuntimeError("Storage safety threshold reached; incomplete scenario")
            with engine.begin() as conn:
                conn.execute(text("""
                INSERT INTO opportunities (id,fingerprint,data,first_discovered,last_verified,catalog_scope,projection_version,authority_rank,kind,company_key,location_key,search_document,remote_flag,active_flag,deadline_at,expires_at,sort_at)
                SELECT 'synthetic-'||lpad(i::text,8,'0'), md5(i::text)||md5('lab'||i),
                  json_build_object('title','SYNTHETIC Software Engineering Intern','company',CASE WHEN i%97=0 THEN 'SYNTHETIC Rare Labs' ELSE 'SYNTHETIC Employer' END,
                    'location','Pune, India','remote',i%2=0,'opportunity_type','internship','url','https://synthetic.example.invalid/role/'||i,
                    'description','SYNTHETIC internship. Undergraduate students graduating in 2029. Python and SQL. '||CASE WHEN i%97=0 THEN 'PyTorch research.' ELSE 'Cloud engineering.' END,
                    'skills',json_build_array('Python','SQL'),'source','local_test','is_demo',true,'active',true,'deadline','2099-01-01T00:00:00Z'),
                  '2026-01-01T00:00:00+00:00','2026-01-01T00:00:00+00:00','public',1,2,'internship',
                  CASE WHEN i%97=0 THEN 'synthetic rare labs' ELSE 'synthetic employer' END,'pune, india',
                  'synthetic software engineering intern python sql pune india '||CASE WHEN i%97=0 THEN 'pytorch rare labs' ELSE 'cloud employer' END,
                  i%2=0,true,'2099-01-01'::timestamptz,'2099-01-01'::timestamptz,'2026-01-01'::timestamptz + i*interval '1 second'
                FROM generate_series(CAST(:lo AS integer),CAST(:hi AS integer)) i
                """), {"lo": offset, "hi": min(args.records, offset + 5000) - 1})
                conn.execute(text("""INSERT INTO source_opportunities(source_id,opportunity_id)
                    SELECT 'synthetic-source-'||lpad((i%1000)::text,4,'0'),'synthetic-'||lpad(i::text,8,'0') FROM generate_series(CAST(:lo AS integer),CAST(:hi AS integer)) i"""), {"lo": offset, "hi": min(args.records, offset + 5000) - 1})
        build_indexes(engine)
        with engine.begin() as conn:
            conn.exec_driver_sql("ANALYZE")
        report = {"at": datetime.now(UTC).isoformat(), "synthetic_only": True, "external_actions": 0,
            "records": args.records, "configured_sources": 1000, "users": 20, "per_user_visible_records": args.records // 20,
            "seed_and_index_seconds": time.perf_counter() - seed_started, "platform": platform.platform(),
            "cpu_count": os.cpu_count(), "resource_limits": {p: Path('/sys/fs/cgroup/' + p).read_text().strip() if Path('/sys/fs/cgroup/' + p).exists() else None for p in ['cpu.max', 'memory.max']},
            "note": "Local closed HTTP workload, one API process, warm caches, no TLS/Redis/provider calls. Not production or internet crawler capacity certification."}
        with engine.connect() as conn:
            report["postgres_version"] = conn.scalar(text("SHOW server_version"))
            report["postgres_settings"] = dict(conn.execute(text("SELECT name,setting FROM pg_settings WHERE name IN ('shared_buffers','max_connections','work_mem','max_wal_size')")).all())
            report["schema_bytes"] = int(conn.scalar(text("SELECT sum(pg_total_relation_size(quote_ident(schemaname)||'.'||quote_ident(tablename))) FROM pg_tables WHERE schemaname=:schema"), {"schema": schema}))
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0));port = sock.getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        log = Path(directory) / "api.log"
        with log.open('w') as stream:
            process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--synthetic-server", str(port)], cwd=ROOT, env=os.environ.copy(), stdout=stream, stderr=stream)
            import httpx
            with httpx.Client(base_url=origin, trust_env=False, timeout=2) as http:
                for _ in range(100):
                    if process.poll() is not None:
                        raise RuntimeError("Fixture API exited: " + log.read_text()[-2000:])
                    try:
                        if http.get('/api/health').status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(.1)
                else:
                    raise RuntimeError("Fixture API readiness timeout")
            for a in accounts:
                with httpx.Client(base_url=origin, trust_env=False, cookies={"internpilot_session": a['token']}, timeout=30) as warm:
                    assert warm.get('/api/v2/opportunities').status_code == 200
            pids = [process.pid]
            pidfile = args.pg_data_dir / "postmaster.pid"
            if pidfile.exists():
                pids.append(int(pidfile.read_text().splitlines()[0]))
            sampler = Sampler(pids);thread = threading.Thread(target=sampler.run, daemon=True);thread.start()
            try:
                report["http"] = asyncio.run(load(origin, accounts, args.concurrency, args.seconds))
            finally:
                report["resources"] = sampler.finish();thread.join(timeout=2)
            with httpx.Client(base_url=origin, trust_env=False, timeout=10) as http:
                report["sql"] = http.get('/_synthetic_lab/metrics').json()
            process.terminate();process.wait(timeout=10);process = None
        report["queue"] = queue_probe(SessionLocal, args.queue_tasks)
        report["catalog_comparison"] = compare_catalog(SessionLocal, accounts[0])
        from app.catalog_query import indexed_query
        plans = {}
        with engine.connect() as conn:
            for name, query in [("newest", indexed_query(accounts[0]['id']).order_by(Opportunity.sort_at.desc(), Opportunity.id.desc())),
                    ("fts", indexed_query(accounts[0]['id'], search="pytorch", search_mode="text"))]:
                compiled = str(query.limit(20).compile(engine, compile_kwargs={"literal_binds": True}))
                plans[name] = conn.exec_driver_sql("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + compiled).scalar()
            report["plans"] = plans
            report["database_table_stats"] = [dict(row) for row in conn.execute(text("SELECT relname,seq_scan,idx_scan,n_tup_ins,n_tup_upd,n_live_tup FROM pg_stat_user_tables WHERE schemaname=:schema"), {"schema": schema}).mappings()]
        report["correctness_passed"] = report["http"]["error_rate"] == 0 and report["queue"]["final_depth"] == 0
        report["workload_class"] = "short_closed_workload_smoke"
        report["production_acceptance_certified"] = False
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({"records": args.records, "http": report['http'], "queue": report['queue'], "resources": report['resources'], "report": str(args.output)}))
        engine.dispose()
        if not report["correctness_passed"]:
            raise SystemExit(1)
    finally:
        if process and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill();process.wait()
        with admin.begin() as conn:
            conn.exec_driver_sql('DROP SCHEMA "' + schema + '" CASCADE')
        admin.dispose()


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--synthetic-server":
        if not os.environ.get("DATA_DIR", "").startswith(tempfile.gettempdir() + "/internpilot-phase7-") or "phase7_lab_" not in os.environ.get("DATABASE_URL", ""):
            raise SystemExit("Only the isolated benchmark driver can start this server")
        sys.path.insert(0, str(ROOT / "backend"))
        server(int(sys.argv[2]))
    else:
        main()
