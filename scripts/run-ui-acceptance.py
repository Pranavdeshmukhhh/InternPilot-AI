"""Run browser acceptance with fresh local data, never the user's configuration.

Build frontend first. Run with backend/.venv/bin/python (Windows: Scripts/python).
The local test portal is authorized to receive synthetic data only.
"""
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
    for port in (8000,3000):
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            try:
                sock.bind(("127.0.0.1",port))
            except OSError:
                raise SystemExit(f"Local port {port} is already in use. Stop that service before isolated UI acceptance.") from None
    node = shutil.which("node")
    if not node or not (ROOT/"frontend/.next/BUILD_ID").exists():
        raise SystemExit("Install frontend dependencies and run npm run build first.")
    processes,logs = [],[]
    with tempfile.TemporaryDirectory(prefix="internpilot-ui-") as directory:
        env = {**os.environ,"DATA_DIR":directory,"DATABASE_URL":f"sqlite:///{Path(directory)/'test.db'}",
               "ENCRYPTION_KEY":Fernet.generate_key().decode(),"ENVIRONMENT":"development","TEST_MODE":"true",
               "TEST_PORTAL_ORIGIN":"http://127.0.0.1:8000","ALLOW_REGISTRATION":"true","REGISTRATION_TOKEN":"",
               "COOKIE_SECURE":"false","CORS_ORIGINS":"http://127.0.0.1:3000","REDIS_URL":"",
               "LLM_PROVIDER":"disabled","WORKER_HEARTBEAT_FILE":"","INTERNAL_API_URL":"http://127.0.0.1:8000",
               "UI_TEST_URL":"http://127.0.0.1:3000","UI_TEST_ALLOW_OWNER_CLI":"true","NO_PROXY":"localhost,127.0.0.1,::1","no_proxy":"localhost,127.0.0.1,::1"}
        # Synthetic tests never inherit live notification or model credentials.
        for key in ("SMTP_HOST","SMTP_PASSWORD","TELEGRAM_BOT_TOKEN","TWILIO_ACCOUNT_SID","TWILIO_AUTH_TOKEN","LLM_API_KEY","BRAVE_SEARCH_API_KEY"):
            env.pop(key,None)
        commands = [
            ([sys.executable,"-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8000"],ROOT/"backend",8000),
            ([node,"node_modules/next/dist/bin/next","start","--hostname","127.0.0.1","--port","3000"],ROOT/"frontend",3000),
            ([sys.executable,"-m","app.worker"],ROOT/"backend",None),
        ]
        try:
            for index,(command,cwd,port) in enumerate(commands):
                log = (Path(directory)/f"process-{index}.log").open("w+")
                logs.append(log)
                process = subprocess.Popen(command,cwd=cwd,env=env,stdout=log,stderr=log,start_new_session=os.name!="nt")
                processes.append(process)
                if port:
                    with httpx.Client(trust_env=False,timeout=2) as client:
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
            return subprocess.call([sys.executable,str(ROOT/"scripts/ui_acceptance.py")],cwd=ROOT,env=env)
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
