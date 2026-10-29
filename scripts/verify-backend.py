"""Run backend checks with disposable data/keys and outbound credentials cleared.

Optional --postgres enables PG variants through PHASE4_POSTGRES_URL after local
synthetic-database validation. Pytest arguments follow --. No real actions run.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--postgres", action="store_true")
    parser.add_argument("--output-prefix", type=Path, default=ROOT / "artifacts/phase7-backend")
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    from cryptography.fernet import Fernet
    env = dict(os.environ)
    pg = os.getenv("PHASE4_POSTGRES_URL", "") if args.postgres else ""
    if args.postgres:
        from sqlalchemy import create_engine, text
        from sqlalchemy.engine import make_url
        parsed = make_url(pg)
        if parsed.host not in {"localhost", "127.0.0.1"} or not (parsed.database or "").startswith(("phase4_", "phase7_")):
            parser.error("PostgreSQL checks require a disposable local phase4_/phase7_ database")
        engine = create_engine(pg)
        with engine.connect() as conn:
            marker = conn.scalar(text("SELECT shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()"))
            if marker not in {"InternPilot Phase4 synthetic benchmark only", "InternPilot Phase7 synthetic benchmark only"} or conn.scalar(text("SELECT rolsuper FROM pg_roles WHERE rolname=current_user")):
                parser.error("PostgreSQL synthetic database marker/non-superuser required")
        engine.dispose()
    prefix = args.output_prefix.resolve()
    prefix.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="internpilot-verify-") as directory:
        env.update(DATA_DIR=directory, DATABASE_URL=f"sqlite:///{directory}/lab.db", ENCRYPTION_KEY=Fernet.generate_key().decode(),
            ENCRYPTION_SECRET="", ENVIRONMENT="development", TEST_MODE="true", TEST_PORTAL_ORIGIN="http://127.0.0.1:8000",
            REDIS_URL="", PHASE4_POSTGRES_URL=pg, DATABASE_SSLMODE="", COOKIE_SECURE="false", ALLOW_REGISTRATION="true",
            REGISTRATION_TOKEN="", INVITATION_ONLY="false", PUBLIC_ORIGIN="", RENDER_EXTERNAL_URL="", WORKER_HEARTBEAT_FILE="",
            CORS_ORIGINS="http://localhost:3000,http://127.0.0.1:3000", LLM_PROVIDER="disabled", LLM_ALLOW_LOCAL="false",
            WORKER_CONCURRENCY="2", BROWSER_CONCURRENCY="1", PYTHONUNBUFFERED="1")
        env.update(AUTH_ADDRESS_LIMIT="20", AUTH_GLOBAL_LIMIT="5000")
        for key in ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM", "GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REDIRECT_URI",
            "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_WHATSAPP_FROM", "TELEGRAM_BOT_TOKEN", "BRAVE_SEARCH_API_KEY", "LLM_API_KEY",
            "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY", "AZURE_OPENAI_API_KEY", "SERPAPI_API_KEY", "TAVILY_API_KEY"]:
            env[key] = ""
        pytest_args = args.pytest_args[1:] if args.pytest_args[:1] == ["--"] else args.pytest_args
        command = [sys.executable, "-m", "pytest", "--junitxml=" + str(prefix) + ".xml", *pytest_args]
        started = time.perf_counter()
        with Path(str(prefix) + ".log").open("w") as log:
            completed = subprocess.run(command, cwd=ROOT / "backend", env=env, stdout=log, stderr=subprocess.STDOUT, check=False)
        report = {"returncode": completed.returncode, "seconds": time.perf_counter() - started, "postgres_variants": bool(pg),
            "isolated_data": True, "external_actions_authorized": False, "command": ["python", *command[1:]]}
        Path(str(prefix) + ".json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report))
        raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
