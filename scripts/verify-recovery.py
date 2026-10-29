"""Real encrypted pg_dump/decrypt/pg_restore drill in two disposable databases.

Requires PHASE7_ADMIN_URL (local cluster admin), PHASE7_POSTGRES_URL (local lab
non-superuser), --pg-data-dir and --confirm-synthetic-only. Only randomly named
phase7_restore_* databases created by this invocation are dropped. Never use a
production cluster. No workers, provider calls or outbound actions are started.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
SEED = '''
from app.migrate import migrate
from app.database import SessionLocal
from app.models import User, Source, Opportunity, SourceOpportunity, Document, Application, CoordinationState, Task
from app.security import digest, encrypt, encrypt_bytes
from app.schemas import Profile, Policy
migrate()
with SessionLocal() as db:
 db.add(User(id="restore-candidate",email_hash=digest("restore@example.invalid"),email_encrypted=encrypt("restore@example.invalid"),password_hash="unused-synthetic",profile_encrypted=encrypt(Profile(name="Synthetic restore candidate").model_dump()),policy_encrypted=encrypt(Policy(emergency_stop=True).model_dump())))
 db.add(Source(id="restore-source",owner_id="restore-candidate",kind="test",company="SYNTHETIC disabled",enabled=False,permitted=False))
 db.add(Opportunity(id="restore-opportunity",fingerprint=digest("restore-fixture"),data={"title":"SYNTHETIC internship","url":"https://synthetic.example.invalid/restore","description":"Synthetic restore drill."}))
 db.flush()
 db.add(SourceOpportunity(source_id="restore-source",opportunity_id="restore-opportunity"))
 db.add(Document(id="restore-document",owner_id="restore-candidate",opportunity_id="restore-opportunity",filename="resume.txt",kind="original",content_encrypted=encrypt_bytes(b"Synthetic verified candidate facts"),metadata_encrypted=encrypt({"synthetic":True})))
 db.add(Application(id="restore-application",owner_id="restore-candidate",opportunity_id="restore-opportunity",document_id="restore-document",status="needs_input"))
 db.add(Task(owner_id="restore-candidate",kind="discovery",payload={"source_id":"restore-source"},dedupe_key="restore-read-only"))
 db.add(CoordinationState(key="workers",value={"paused":True}))
 db.commit()
'''
VERIFY = '''
import hashlib,json
from sqlalchemy import select
from app.migrate import migrate
from app.database import SessionLocal
from app.models import User, Document, Application, SchemaVersion
from app.security import decrypt,decrypt_bytes
from app.worker import claim_task
migrate();migrate()
with SessionLocal() as db:
 user=db.get(User,"restore-candidate");doc=db.get(Document,"restore-document");app=db.get(Application,"restore-application")
 assert decrypt(user.profile_encrypted)["name"]=="Synthetic restore candidate"
 assert decrypt_bytes(doc.content_encrypted)==b"Synthetic verified candidate facts"
 assert app.document_id==doc.id and app.opportunity_id==doc.opportunity_id=="restore-opportunity"
 assert decrypt(user.policy_encrypted)["emergency_stop"] is True
 print(json.dumps({"versions":list(db.scalars(select(SchemaVersion.version).order_by(SchemaVersion.version))),"profile_cipher_sha256":hashlib.sha256(user.profile_encrypted).hexdigest(),"document_cipher_sha256":hashlib.sha256(doc.content_encrypted).hexdigest(),"application_id":app.id,"document_id":doc.id,"application_status":app.status}))
assert claim_task("restore-must-not-execute") is None
'''


def run(command, env):
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=60, check=False)
    if result.returncode:
        # Commands may contain database names; provider passwords are env-only.
        raise RuntimeError("Isolated recovery step failed: " + result.stderr[-1500:])
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pg-data-dir", type=Path, required=True)
    parser.add_argument("--confirm-synthetic-only", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/phase7-recovery.json")
    args = parser.parse_args()
    if not args.confirm_synthetic_only:
        parser.error("Explicit synthetic-only confirmation required")
    from cryptography.fernet import Fernet
    from psycopg import sql
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    admin_url, lab_url = (os.environ.get(key, "") for key in ["PHASE7_ADMIN_URL", "PHASE7_POSTGRES_URL"])
    lab = make_url(lab_url)
    adm = make_url(admin_url)
    if lab.host not in {"localhost", "127.0.0.1"} or not (lab.database or "").startswith(("phase4_", "phase7_")):
        parser.error("A marked local lab database is required")
    if adm.host not in {None, "localhost", "127.0.0.1"} or not (args.pg_data_dir / "PG_VERSION").exists():
        parser.error("A local disposable PostgreSQL cluster is required")
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    check_engine = create_engine(lab_url)
    with check_engine.connect() as conn:
        marker = conn.scalar(text("SELECT shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()"))
        if marker not in {"InternPilot Phase4 synthetic benchmark only", "InternPilot Phase7 synthetic benchmark only"}:
            parser.error("Missing synthetic database marker")
    check_engine.dispose()
    created = []
    started = time.perf_counter()
    try:
      with engine.connect() as conn, tempfile.TemporaryDirectory(prefix="internpilot-restore-") as directory:
        if Path(conn.scalar(text("SHOW data_directory"))).resolve() != args.pg_data_dir.resolve():
            parser.error("Admin cluster data_directory does not match the explicitly selected lab")
        names = ["phase7_restore_" + uuid4().hex[:12] for _ in range(2)]
        for name in names:
            conn.connection.driver_connection.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(name), sql.Identifier(lab.username)))
            created.append(name)
        env = dict(os.environ)
        env.update(PYTHONPATH=str(ROOT / "backend"), DATA_DIR=directory, ENCRYPTION_KEY=Fernet.generate_key().decode(), ENCRYPTION_SECRET="",
            ENVIRONMENT="development", COOKIE_SECURE="false", TEST_MODE="false", DATABASE_SSLMODE="", REDIS_URL="", WORKER_HEARTBEAT_FILE="",
            LLM_PROVIDER="disabled", LLM_API_KEY="", BRAVE_SEARCH_API_KEY="", GMAIL_CLIENT_ID="", GMAIL_CLIENT_SECRET="", SMTP_HOST="",
            SMTP_PASSWORD="", TELEGRAM_BOT_TOKEN="", TWILIO_AUTH_TOKEN="", PHASE7_ADMIN_URL="", PHASE7_POSTGRES_URL="")
        env["DATABASE_URL"] = lab.set(database=names[0]).render_as_string(hide_password=False)
        run([sys.executable, "-c", SEED], env)
        before = json.loads(run([sys.executable, "-c", VERIFY], env))
        backup, decrypted = Path(directory) / "database.ipbk", Path(directory) / "database.dump"
        dump_started = time.perf_counter()
        run([sys.executable, "scripts/secure-backup.py", str(backup)], env)
        backup_seconds = time.perf_counter() - dump_started
        restore_started = time.perf_counter()
        run([sys.executable, "scripts/secure-backup.py", str(decrypted), "--decrypt", str(backup)], env)
        pg_env = dict(env, PGHOST=lab.host, PGPORT=str(lab.port or 5432), PGUSER=lab.username, PGPASSWORD=lab.password or "", PGCONNECT_TIMEOUT="10")
        run(["pg_restore", "--no-owner", "--no-acl", "--exit-on-error", "--dbname=" + names[1], str(decrypted)], pg_env)
        env["DATABASE_URL"] = lab.set(database=names[1]).render_as_string(hide_password=False)
        after = json.loads(run([sys.executable, "-c", VERIFY], env))
        assert before == after
        restore_seconds = time.perf_counter() - restore_started
        # The command must remove incomplete plaintext on authentication failure.
        corrupt = bytearray(backup.read_bytes());corrupt[-1] ^= 1
        tampered = Path(directory) / "tampered.ipbk";tampered.write_bytes(corrupt)
        rejected = Path(directory) / "must-not-survive.dump"
        failure = subprocess.run([sys.executable, "scripts/secure-backup.py", str(rejected), "--decrypt", str(tampered)], cwd=ROOT, env=env, capture_output=True, timeout=15, check=False)
        assert failure.returncode != 0 and not rejected.exists()
        report = {"synthetic_only": True, "passed": True, "databases_created": 2, "schema_versions": after["versions"],
            "encrypted_backup_bytes": backup.stat().st_size, "backup_seconds": backup_seconds, "restore_and_verify_seconds": restore_seconds,
            "roundtrip_wall_seconds": time.perf_counter() - started, "ciphertext_preserved": True, "references_preserved": True,
            "document_decryption_verified": True, "workers_remain_paused": True, "tampering_rejected_and_partial_plaintext_removed": True,
            "note": "Small logical backup/restore smoke on local PostgreSQL. Not PITR, full-size RTO/RPO, object storage, offsite or HA recovery certification."}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report))
    finally:
        with engine.connect() as conn:
            for name in created:
                conn.connection.driver_connection.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
        engine.dispose()


if __name__ == "__main__":
    main()
