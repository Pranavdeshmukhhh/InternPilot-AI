"""Run browser acceptance with fresh local data, never the user's configuration.

Build frontend first. Run with backend/.venv/bin/python (Windows: Scripts/python).
The local test portal is authorized to receive synthetic data only.
"""
import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--regional",action="store_true",help="Run the regional browsing acceptance checks instead")
    parser.add_argument("--production-ui",action="store_true",help="Run the production upgrade browser suite instead")
    parser.add_argument("--source-discovery-ui",action="store_true",help="Run source review browser checks without starting a crawl worker")
    parser.add_argument("--warm-ui",action="store_true",help="Run warm-theme and browsing acceptance without a crawl worker")
    parser.add_argument("--studio-ui",action="store_true",help="Run studio interface acceptance without a crawl worker")
    parser.add_argument("--phase6-ui",action="store_true",help="Offline product UX, accessibility and request-budget acceptance")
    parser.add_argument("--phase6-baseline",action="store_true",help="Measure audited pre-redesign frontend in isolation")
    parser.add_argument("--public-ui",action="store_true",help="Public landing/demo and in-app mobile smoke; no crawlers")
    parser.add_argument("--access-ui",action="store_true",help="Owner-issued invitations, sign-in and Terms motion; no crawlers")
    parser.add_argument("--founder-ui",action="store_true",help="Private founder reports, MFA and recovery; synthetic data only")
    parser.add_argument("--user-journey",action="store_true",help="Browser journey with application-only worker and local test portal")
    arguments = parser.parse_args()
    frontend = Path(os.getenv("UI_TEST_FRONTEND_DIR", str(ROOT / "frontend")))
    for port in (8000,3000):
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            try:
                sock.bind(("127.0.0.1",port))
            except OSError:
                raise SystemExit(f"Local port {port} is already in use. Stop that service before isolated UI acceptance.") from None
    node = shutil.which("node")
    if not node or not (frontend/".next/BUILD_ID").exists():
        raise SystemExit("Install frontend dependencies and run npm run build first.")
    processes,logs = [],[]
    with tempfile.TemporaryDirectory(prefix="internpilot-ui-") as directory:
        env = {**os.environ,"DATA_DIR":directory,"DATABASE_URL":f"sqlite:///{Path(directory)/'test.db'}",
               "ENCRYPTION_KEY":Fernet.generate_key().decode(),"ENVIRONMENT":"development","TEST_MODE":"true",
               "TEST_PORTAL_ORIGIN":"http://127.0.0.1:8000","ALLOW_REGISTRATION":"true","REGISTRATION_TOKEN":"","INVITATION_ONLY":"false",
               "COOKIE_SECURE":"false","CORS_ORIGINS":"http://127.0.0.1:3000","REDIS_URL":"",
               "LLM_PROVIDER":"disabled","WORKER_HEARTBEAT_FILE":"","INTERNAL_API_URL":"http://127.0.0.1:8000",
               "UI_TEST_URL":"http://127.0.0.1:3000","UI_TEST_ALLOW_OWNER_CLI":"true","NO_PROXY":"localhost,127.0.0.1,::1","no_proxy":"localhost,127.0.0.1,::1"}
        # Synthetic tests never inherit live notification or model credentials.
        if arguments.access_ui:
            env["INVITATION_ONLY"]="true"
        if arguments.user_journey:
            env["WORKER_KINDS"]="application"
            env["WORKER_CONCURRENCY"]="1"
        for key in ("SMTP_HOST","SMTP_PASSWORD","TELEGRAM_BOT_TOKEN","TWILIO_ACCOUNT_SID","TWILIO_AUTH_TOKEN","LLM_API_KEY","BRAVE_SEARCH_API_KEY","GMAIL_CLIENT_ID","GMAIL_CLIENT_SECRET","GMAIL_REDIRECT_URI"):
            env[key]=""  # Also prevents dotenv from reloading real provider secrets.
        commands = [
            ([sys.executable,"-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8000"],ROOT/"backend",8000),
            ([node,"node_modules/next/dist/bin/next","start","--hostname","127.0.0.1","--port","3000"],frontend,3000),
            ([sys.executable,"-m","app.worker"],ROOT/"backend",None),
        ]
        if arguments.founder_ui or arguments.access_ui or arguments.public_ui or arguments.source_discovery_ui or arguments.warm_ui or arguments.studio_ui or arguments.phase6_ui or arguments.phase6_baseline:
            commands = commands[:2]
        try:
            for index,(command,cwd,port) in enumerate(commands):
                log = (Path(directory)/f"process-{index}.log").open("w+")
                logs.append(log)
                process = subprocess.Popen(command,cwd=cwd,env=env,stdout=log,stderr=log,start_new_session=os.name!="nt")
                processes.append(process)
                if port:
                    with httpx.Client(trust_env=False,timeout=2,follow_redirects=True) as client:
                        for _ in range(150):
                            if process.poll() is not None:
                                raise RuntimeError(f"Isolated process {index} exited during startup")
                            try:
                                path = "/api/health" if port==8000 else "/"
                                if client.get(f"http://127.0.0.1:{port}"+path).status_code==200:
                                    break
                            except httpx.HTTPError:
                                pass
                            time.sleep(0.2)
                        else:
                            raise RuntimeError(f"Isolated service on port {port} did not become ready")
            driver = "user-journey.py" if arguments.user_journey else "founder-ui.py" if arguments.founder_ui else "access-ui.py" if arguments.access_ui else "public-ui.py" if arguments.public_ui else "phase6-ui.py" if arguments.phase6_ui or arguments.phase6_baseline else "studio-ui.py" if arguments.studio_ui else "warm-ui.py" if arguments.warm_ui else "source-discovery-ui.py" if arguments.source_discovery_ui else "production_ui.py" if arguments.production_ui else "regional_ui.py" if arguments.regional else "ui_acceptance.py"
            env["PHASE6_BASELINE"] = "true" if arguments.phase6_baseline else "false"
            return subprocess.call([sys.executable,str(ROOT/"scripts"/driver)],cwd=ROOT,env=env)
        finally:
            for process in reversed(processes):
                if process.poll() is None:
                    if os.name!="nt":
                        os.killpg(process.pid,signal.SIGTERM)
                    else:
                        process.terminate()
                    try:
                        process.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        process.kill(); process.wait(timeout=5)
            for log in logs:
                log.close()


if __name__=="__main__":
    raise SystemExit(main())
