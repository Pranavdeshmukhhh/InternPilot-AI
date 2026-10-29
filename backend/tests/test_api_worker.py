"""API, encryption and crash-recovery acceptance against an isolated local stack.

Each test starts a real FastAPI process and uses a fresh SQLite database and key.
Worker invocations run in separate processes to verify durable restart behavior.
Only the authorized local test portal receives synthetic application data.
"""
from __future__ import annotations

import hashlib
import json
import os
import signal
import socket
import sqlite3
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest
from cryptography.fernet import Fernet

BACKEND = Path(__file__).parents[1]
PASSWORD = "synthetic-only-password-2049!"


def _stop_group(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    if hasattr(os, "killpg"):
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


class LocalStack:
    def __init__(self, origin, directory, env):
        self.origin, self.directory, self.env = origin, directory, env
        self.clients = []

    def client(self):
        client = httpx.Client(base_url=self.origin, trust_env=False, timeout=30)
        self.clients.append(client)
        return client

    def register(self, address="candidate@example.invalid"):
        client = self.client()
        response = client.post("/api/auth/register", json={"email": address, "password": PASSWORD})
        assert response.status_code == 200, response.text
        result = response.json()
        client.headers["X-CSRF-Token"] = result["csrf_token"]
        return client, result

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.directory / "internpilot.db", timeout=20)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def python(self, script, expected=0):
        process = subprocess.Popen(
            [sys.executable, "-c", script], cwd=BACKEND, env=self.env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=os.name != "nt", text=True,
        )
        try:
            stdout, stderr = process.communicate(timeout=70)
            assert process.returncode == expected, f"Isolated worker exited {process.returncode}: {stderr}\n{stdout}"
            return stdout.strip()
        finally:
            _stop_group(process)

    def worker_once(self):
        return json.loads(self.python("""
import asyncio, json
from app.worker import claim_task, execute_task
row = claim_task('acceptance-worker')
if row:
    asyncio.run(execute_task(row, 'acceptance-worker'))
print(json.dumps(row))
"""))

    def expire_lease(self):
        with self.db() as db:
            db.execute("UPDATE tasks SET lease_until='2000-01-01T00:00:00+00:00' WHERE status='running'")

    def recover(self):
        return int(self.python("from app.worker import recover_expired; print(recover_expired())"))


@pytest.fixture
def stack(tmp_path, request):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"
    key = Fernet.generate_key().decode()
    env = {
        **os.environ, "DATA_DIR": str(tmp_path),
        "DATABASE_URL": f"sqlite:///{tmp_path / 'internpilot.db'}", "ENCRYPTION_KEY": key,
        "TEST_MODE": "true", "TEST_PORTAL_ORIGIN": origin,
        "ALLOW_REGISTRATION": "true", "COOKIE_SECURE": "false",
        "CORS_ORIGINS": "http://localhost:3000", "REDIS_URL": "", "LLM_PROVIDER": "disabled",
        "REGISTRATION_TOKEN": "", "INVITATION_ONLY":"false", "ENVIRONMENT": "development", "DATABASE_SSLMODE": "",
        "WORKER_HEARTBEAT_FILE": "",
    }
    for key in ("GMAIL_CLIENT_ID","GMAIL_CLIENT_SECRET","GMAIL_REDIRECT_URI","BRAVE_SEARCH_API_KEY","SMTP_HOST","SMTP_PASSWORD","TELEGRAM_BOT_TOKEN","TWILIO_ACCOUNT_SID","TWILIO_AUTH_TOKEN","LLM_API_KEY"):
        env[key]=""
    env.update({key: str(value).replace("{data_dir}", str(tmp_path)) for key, value in getattr(request, "param", {}).items()})
    log = (tmp_path / "api.log").open("w+")
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "error"],
        cwd=BACKEND, env=env, stdout=log, stderr=log, start_new_session=os.name != "nt",
    )
    local = LocalStack(origin, tmp_path, env)
    try:
        with httpx.Client(trust_env=False, timeout=2) as client:
            for _ in range(100):
                if process.poll() is not None:
                    log.seek(0)
                    pytest.fail(f"Isolated API startup failed: {log.read()}")
                try:
                    if client.get(origin + "/api/health").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.1)
            else:
                pytest.fail("Isolated API did not become ready")
        yield local
    finally:
        for client in local.clients:
            client.close()
        _stop_group(process)
        log.close()


def test_auth_csrf_explicit_policy_and_encrypted_profile(stack):
    anonymous = stack.client()
    assert anonymous.get("/api/profile").status_code == 401
    client, account = stack.register()
    assert client.get("/api/auth/session").json()["user"]["id"] == account["user"]["id"]
    default_profile = client.get("/api/profile").json()
    assert default_profile["graduation_year"] == 2029
    assert default_profile["country"] == "India"
    assert "email" not in default_profile["verified_fields"]
    profile = {**default_profile, "name": "Synthetic Verified Candidate", "verified_fields": ["name", "country", "graduation_year"]}
    without_csrf = stack.client()
    without_csrf.cookies.update(client.cookies)
    assert without_csrf.put("/api/profile", json=profile).status_code == 403
    assert client.put("/api/profile", json=profile, headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert client.put("/api/profile", json=profile, headers={"Origin": "https://untrusted.invalid"}).status_code == 403
    assert client.put("/api/profile", json=profile).status_code == 200
    invalid_policy = {**client.get("/api/policy").json(), "mode": "auto"}
    assert client.put("/api/policy", json=invalid_policy).status_code == 422
    assert client.get("/api/policy").json()["mode"] == "discovery"
    with stack.db() as db:
        user = db.execute("SELECT * FROM users").fetchone()
        assert user["password_hash"].startswith("scrypt$")
        assert PASSWORD not in user["password_hash"]
        assert b"Synthetic Verified Candidate" not in user["profile_encrypted"]
        assert b"candidate@example.invalid" not in user["email_encrypted"]
        decoded = json.loads(Fernet(stack.env["ENCRYPTION_KEY"].encode()).decrypt(user["profile_encrypted"]))
        assert decoded["name"] == profile["name"]
        session = db.execute("SELECT * FROM sessions").fetchone()
        assert session["token_hash"] != client.cookies.get("internpilot_session")
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/profile").status_code == 401
    assert client.post("/api/auth/login", json={"email": "candidate@example.invalid", "password": PASSWORD + "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "candidate@example.invalid", "password": PASSWORD}).status_code == 200


def test_owner_boundaries_and_resume_import_never_verifies_facts(stack):
    owner, _ = stack.register("owner@example.invalid")
    other, _ = stack.register("other@example.invalid")
    before = owner.get("/api/profile").json()
    uploaded = owner.post("/api/documents/upload", files={"file": ("../../resume.txt", b"Synthetic resume\nExpected graduation: 2028\nSkills: Python\nimported@example.invalid", "text/plain")})
    assert uploaded.status_code == 200, uploaded.text
    document = uploaded.json()
    assert document["filename"] == "resume.txt"
    assert document["verified"] is False
    assert document["verified_fields"] == []
    assert owner.get("/api/profile").json() == before
    assert other.get(f'/api/documents/{document["id"]}/download').status_code == 404
    assert other.get("/api/documents").json() == []
    source_id = owner.get("/api/sources").json()[0]["id"]
    assert other.patch(f"/api/sources/{source_id}", json={"enabled": False}).status_code == 404
    assert other.delete(f"/api/sources/{source_id}").status_code == 404
    demo = owner.post("/api/demo/run").json()["application"]
    assert other.post(f'/api/applications/{demo["id"]}/retry').status_code == 404
    assert other.patch(f'/api/applications/{demo["id"]}', json={"status": "interview"}).status_code == 404
    assert other.get(f'/api/opportunities/{demo["opportunity_id"]}').status_code == 404
    assert other.get("/api/applications").json() == []
    assert owner.post("/api/emergency-stop", json={"stopped": True}).status_code == 200
    notification_id = owner.get("/api/notifications").json()[0]["id"]
    assert other.patch(f"/api/notifications/{notification_id}", json={"read": True}).status_code == 404
    with stack.db() as db:
        blob = db.execute("SELECT content_encrypted FROM documents WHERE id=?", (document["id"],)).fetchone()[0]
        assert b"imported@example.invalid" not in blob


def test_real_worker_demo_confirms_upload_screenshot_and_prevents_duplicates(stack):
    client, _ = stack.register()
    profile_before = client.get("/api/profile").json()
    response = client.post("/api/demo/run")
    assert response.status_code == 200, response.text
    queued = response.json()
    assert queued["duplicate_prevented"] is False
    application_id = queued["application"]["id"]
    task = stack.worker_once()
    assert task["id"] == queued["task"]["id"]
    application = client.get("/api/applications").json()[0]
    assert application["id"] == application_id
    assert application["status"] == "submitted", application["reason"]
    assert application["confirmation_id"].startswith("TEST-")
    screenshot = client.get(f'/api/documents/{application["screenshot_id"]}/download')
    assert screenshot.status_code == 200 and screenshot.content.startswith(b"\x89PNG")
    resume = client.get(f'/api/documents/{application["document_id"]}/download')
    assert resume.status_code == 200 and resume.content.startswith(b"%PDF-")
    receipt = stack.client().get(f'/test-portal/records/{application["confirmation_id"]}').json()
    assert receipt["resume_sha256"] == hashlib.sha256(resume.content).hexdigest()
    assert client.get("/api/profile").json() == profile_before
    again = client.post("/api/demo/run").json()
    assert again["duplicate_prevented"] is True
    assert again["application"]["id"] == application_id
    policy = client.get("/api/policy").json()
    assert client.put("/api/policy", json={**policy, "mode": "assisted"}).status_code == 200
    assert client.post("/api/applications", json={"opportunity_id": application["opportunity_id"]}).status_code == 409
    assert client.post(f"/api/applications/{application_id}/retry").status_code == 409
    notifications = client.get("/api/notifications").json()
    assert any(n["kind"] == "submitted" for n in notifications)
    assert client.get("/api/tasks").json()[0]["status"] == "completed"
    # Local fixtures do not inflate real-employer dashboard counters.
    metrics = client.get("/api/dashboard").json()["metrics"]
    assert metrics["submitted"] == 0 and metrics["opportunities"] == 0
    assert metrics["success_rate"] is None
    cipher = Fernet(stack.env["ENCRYPTION_KEY"].encode())
    with stack.db() as db:
        row = db.execute("SELECT * FROM applications WHERE id=?", (application_id,)).fetchone()
        assert row["submission_started_at"] is not None
        assert row["snapshot_encrypted"] and row["session_encrypted"]
        assert b"InternPilot Test Candidate" not in row["snapshot_encrypted"]
        shot = db.execute("SELECT content_encrypted FROM documents WHERE id=?", (row["screenshot_id"],)).fetchone()[0]
        assert not shot.startswith(b"\x89PNG")
        assert cipher.decrypt(shot) == screenshot.content
        confirmation = json.loads(cipher.decrypt(row["confirmation_encrypted"]))
        assert row["confirmation_id"] in confirmation["text"]
        assert db.execute("SELECT count(*) FROM applications").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM tasks").fetchone()[0] == 1


def test_worker_restart_recovers_pre_submission_then_safely_finishes(stack):
    client, _ = stack.register()
    queued = client.post("/api/demo/run").json()
    application_id = queued["application"]["id"]
    # Abrupt process death occurs after process_application has durably entered
    # preparing, but before the browser can invoke the final-click checkpoint.
    stack.python("""
import asyncio, os
import app.automation as automation
from app.worker import claim_task, execute_task
async def crash_before_browser(**kwargs):
    os._exit(82)
automation.run_application = crash_before_browser
row = claim_task('crashed-before-checkpoint')
asyncio.run(execute_task(row, 'crashed-before-checkpoint'))
""", expected=82)
    with stack.db() as db:
        app = db.execute("SELECT * FROM applications WHERE id=?", (application_id,)).fetchone()
        assert app["status"] == "preparing" and app["submission_started_at"] is None
        task = db.execute("SELECT * FROM tasks").fetchone()
        assert task["status"] == "running" and task["attempts"] == 1
    stack.expire_lease()
    assert stack.recover() == 1
    assert client.get("/api/applications").json()[0]["status"] == "queued"
    resumed = stack.worker_once()
    assert resumed["attempts"] == 2
    result = client.get("/api/applications").json()[0]
    assert result["status"] == "submitted", result["reason"]
    assert result["confirmation_id"]
    assert any(e["kind"] == "worker_recovery" for e in client.get("/api/events").json())


def test_worker_restart_after_durable_screenshot_never_retries_submit(stack):
    client, _ = stack.register()
    application_id = client.post("/api/demo/run").json()["application"]["id"]
    # Use the real browser. Kill this worker immediately after its actual filled
    # screenshot and SUBMITTING state have been committed, before final click.
    stack.python("""
import asyncio, os
import app.automation as automation
from app.worker import claim_task, execute_task
original = automation.run_application
async def crash_after_checkpoint(**kwargs):
    checkpoint = kwargs['before_submit']
    async def durable_then_die(screenshot):
        await checkpoint(screenshot)
        os._exit(83)
    kwargs['before_submit'] = durable_then_die
    return await original(**kwargs)
automation.run_application = crash_after_checkpoint
row = claim_task('crashed-after-checkpoint')
asyncio.run(execute_task(row, 'crashed-after-checkpoint'))
""", expected=83)
    cipher = Fernet(stack.env["ENCRYPTION_KEY"].encode())
    with stack.db() as db:
        row = db.execute("SELECT * FROM applications WHERE id=?", (application_id,)).fetchone()
        assert row["status"] == "submitting" and row["submission_started_at"] is not None
        screenshot = db.execute("SELECT content_encrypted FROM documents WHERE id=?", (row["screenshot_id"],)).fetchone()[0]
        assert cipher.decrypt(screenshot).startswith(b"\x89PNG")
        assert row["confirmation_id"] is None
    stack.expire_lease()
    assert stack.recover() == 1
    row = client.get("/api/applications").json()[0]
    assert row["status"] == "uncertain" and row["confirmation_id"] is None
    assert stack.worker_once() is None
    assert client.get("/api/tasks").json()[0]["status"] == "completed"
    assert client.post(f"/api/applications/{application_id}/retry").status_code == 409
    duplicate = client.post("/api/demo/run").json()
    assert duplicate["duplicate_prevented"] is True and duplicate["application"]["id"] == application_id
    assert any(n["kind"] == "uncertain" for n in client.get("/api/notifications").json())


def test_emergency_stop_blocks_queued_application_before_browser(stack):
    client, _ = stack.register()
    queued = client.post("/api/demo/run").json()
    assert client.post("/api/emergency-stop", json={"stopped": True}).status_code == 200
    assert client.post("/api/demo/run").status_code == 409
    assert client.post("/api/discovery/run").status_code == 409
    assert stack.worker_once()["id"] == queued["task"]["id"]
    app = client.get("/api/applications").json()[0]
    assert app["status"] == "needs_input" and "Emergency stop" in app["reason"]
    assert app["screenshot_id"] is None and app["confirmation_id"] is None
    with stack.db() as db:
        assert db.execute("SELECT submission_started_at FROM applications").fetchone()[0] is None


def test_two_accounts_have_distinct_demo_receipts_and_isolated_resume_uploads(stack):
    """Synthetic identities must be stable per owner, not global across accounts.

    The test portal deduplicates by candidate and requisition. Reusing a single
    synthetic email across accounts would incorrectly return the first owner's
    receipt for a second owner's newly generated PDF.
    """
    first, _ = stack.register("first-owner@example.invalid")
    second, _ = stack.register("second-owner@example.invalid")
    queued_first = first.post("/api/demo/run").json()
    queued_second = second.post("/api/demo/run").json()
    assert queued_first["application"]["id"] != queued_second["application"]["id"]
    assert queued_first["application"]["url"] == queued_second["application"]["url"]
    executed = {stack.worker_once()["id"], stack.worker_once()["id"]}
    assert executed == {queued_first["task"]["id"], queued_second["task"]["id"]}
    first_app = first.get("/api/applications").json()[0]
    second_app = second.get("/api/applications").json()[0]
    assert first_app["status"] == "submitted", first_app["reason"]
    assert second_app["status"] == "submitted", second_app["reason"]
    assert first_app["confirmation_id"] != second_app["confirmation_id"]
    first_pdf = first.get(f'/api/documents/{first_app["document_id"]}/download').content
    second_pdf = second.get(f'/api/documents/{second_app["document_id"]}/download').content
    assert first_pdf.startswith(b"%PDF-") and second_pdf.startswith(b"%PDF-")
    assert hashlib.sha256(first_pdf).hexdigest() != hashlib.sha256(second_pdf).hexdigest()
    assert second.get(f'/api/documents/{first_app["document_id"]}/download').status_code == 404
    assert first.get(f'/api/documents/{second_app["screenshot_id"]}/download').status_code == 404
    public = stack.client()
    for app, pdf in ((first_app, first_pdf), (second_app, second_pdf)):
        receipt = public.get(f'/test-portal/records/{app["confirmation_id"]}').json()
        assert receipt["resume_sha256"] == hashlib.sha256(pdf).hexdigest()
        assert receipt["resume_bytes"] == len(pdf)
    for client, app in ((first, first_app), (second, second_app)):
        duplicate = client.post("/api/demo/run").json()
        assert duplicate["duplicate_prevented"] is True
        assert duplicate["application"]["id"] == app["id"]
        assert len(client.get("/api/applications").json()) == 1
        assert len(client.get("/api/tasks").json()) == 1
    with stack.db() as db:
        assert db.execute("SELECT count(*) FROM applications").fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM tasks").fetchone()[0] == 2
        for app, pdf in ((first_app, first_pdf), (second_app, second_pdf)):
            encrypted = db.execute("SELECT content_encrypted FROM documents WHERE id=?", (app["document_id"],)).fetchone()[0]
            assert not encrypted.startswith(b"%PDF-")
            assert Fernet(stack.env["ENCRYPTION_KEY"].encode()).decrypt(encrypted) == pdf
    with sqlite3.connect(stack.directory / "test-portal.sqlite3") as portal_db:
        assert portal_db.execute("SELECT count(*) FROM submissions").fetchone()[0] == 2
