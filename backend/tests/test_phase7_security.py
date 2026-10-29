"""Defensive local probes. No external requests, credentials or sends."""
import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app import auth_limits, gmail, outreach, document_processing
from app.models import CoordinationState, OutreachContact, OutreachMessage, OutreachReply
from app.security import digest, encrypt
from app.body_limit import BodyLimitMiddleware
from test_distributed_discovery import lab  # noqa: F401
from test_outreach import mailbox  # noqa: F401


def test_auth_admission_is_atomic_shared_and_prunes_expired_windows(lab, monkeypatch):  # noqa: F811
    _, sessions = lab
    monkeypatch.setattr(auth_limits, "SessionLocal", sessions)
    clock = [1800000000]
    monkeypatch.setattr(auth_limits, "time", SimpleNamespace(time=lambda: clock[0]))
    monkeypatch.setattr(auth_limits.settings, "auth_address_limit", 3)
    monkeypatch.setattr(auth_limits.settings, "auth_global_limit", 100)

    def attempt(_):
        try:
            auth_limits.admit("203.0.113.10")
            return 200
        except HTTPException as exc:
            assert "Retry-After" in exc.headers
            return exc.status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(8)))
    assert results.count(200) == 3 and results.count(429) == 5
    clock[0] += 301
    assert attempt(0) == 200
    with sessions() as db:
        rows = list(db.scalars(select(CoordinationState).where(CoordinationState.key.like("auth:%"))))
        assert len(rows) == 2 and all("203.0.113.10" not in r.key for r in rows)


def test_auth_global_budget_bounds_rotating_addresses_and_fails_closed(lab, monkeypatch):  # noqa: F811
    _, sessions = lab
    monkeypatch.setattr(auth_limits, "SessionLocal", sessions)
    monkeypatch.setattr(auth_limits.settings, "auth_global_limit", 2)
    auth_limits.admit("203.0.113.1")
    auth_limits.admit("203.0.113.2")
    with pytest.raises(HTTPException) as rejected:
        auth_limits.admit("203.0.113.3")
    assert rejected.value.status_code == 429
    with sessions() as db:
        assert len(list(db.scalars(select(CoordinationState).where(CoordinationState.key.like("auth:%"))))) == 3

    def unavailable():
        raise OperationalError("synthetic", {}, Exception("not logged"))
    monkeypatch.setattr(auth_limits, "SessionLocal", unavailable)
    with pytest.raises(HTTPException) as outage:
        auth_limits.admit("203.0.113.4")
    assert outage.value.status_code == 503 and "not logged" not in str(outage.value.detail)


def test_followup_refreshes_exact_recipient_outside_background_page_and_after_100_messages(mailbox, monkeypatch):  # noqa: F811
    parent_id = mailbox.message()
    with mailbox.db() as db:
        for i in range(26):
            contact = OutreachContact(owner_id=mailbox.owner, email_hash=digest(str(i)), data_encrypted=encrypt({"email": f"noise{i}@example.invalid"}))
            db.add(contact); db.flush()
            db.add(OutreachMessage(owner_id=mailbox.owner, contact_id=contact.id, status="sent", thread_id=f"noise-{i}",
                content_encrypted=encrypt({}), created_at="2000-01-01T00:00:00+00:00"))
        parent = db.get(OutreachMessage, parent_id)
        parent.status, parent.provider_id, parent.thread_id = "sent", "sent-target", "target-thread"
        db.commit()
    followup = mailbox.message(parent_id=parent_id)
    calls = []

    async def provider(owner, method, path, **kwargs):
        calls.append((method, path))
        assert method == "GET" and path == "threads/target-thread"
        own = {"id": "sent-target", "payload": {"headers": [{"name": "From", "value": "sender@example.invalid"}]}}
        reply = {"id": "late-opt-out", "payload": {"mimeType": "text/plain", "headers": [
            {"name": "From", "value": "recruiter@example.invalid"}], "body": {"data": base64.urlsafe_b64encode(b"stop").decode()}}}
        return {"id": "target-thread", "messages": [own] * 100 + [reply]}

    monkeypatch.setattr(gmail, "request", provider)
    asyncio.run(outreach.send_message(followup))
    assert calls == [("GET", "threads/target-thread")]
    with mailbox.db() as db:
        row = db.get(OutreachMessage, followup)
        assert row.status == "cancelled" and not row.sending_started_at
        assert db.get(OutreachContact, mailbox.contact).status == "opted_out"
        assert db.scalar(select(OutreachReply.kind)) == "opt_out"


@pytest.mark.parametrize("response", [{}, {"messages": "invalid"}, {"messages": [{}]}, {"messages": [{}] * 1001}])
def test_unverifiable_followup_thread_cannot_authorize_send(mailbox, monkeypatch, response):  # noqa: F811
    parent_id = mailbox.message()
    with mailbox.db() as db:
        parent = db.get(OutreachMessage, parent_id)
        parent.status, parent.provider_id, parent.thread_id = "sent", "sent-target", "target-thread"
        db.commit()
    followup = mailbox.message(parent_id=parent_id)

    async def provider(owner, method, path, **kwargs):
        assert method == "GET"
        return response
    monkeypatch.setattr(gmail, "request", provider)
    asyncio.run(outreach.send_message(followup))
    with mailbox.db() as db:
        row = db.get(OutreachMessage, followup)
        assert row.status == "needs_review" and not row.sending_started_at


def test_verified_followup_can_send_once_and_rechecks_the_parent_receipt(mailbox, monkeypatch):  # noqa: F811
    parent_id = mailbox.message()
    with mailbox.db() as db:
        parent = db.get(OutreachMessage, parent_id)
        parent.status, parent.provider_id, parent.thread_id = "sent", "sent-target", "target-thread"
        db.commit()
    followup = mailbox.message(parent_id=parent_id)
    sends = []

    async def provider(owner, method, path, **kwargs):
        if method == "GET":
            return {"id": "target-thread", "messages": [{"id": "sent-target", "payload": {}}]}
        sends.append(path)
        return {"id": "confirmed-followup", "threadId": "target-thread"}
    monkeypatch.setattr(gmail, "request", provider)
    asyncio.run(outreach.send_message(followup))
    asyncio.run(outreach.send_message(followup))
    assert sends == ["messages/send"]
    with mailbox.db() as db:
        assert db.get(OutreachMessage, followup).provider_id == "confirmed-followup"


def test_resume_child_extracts_real_text_without_inheriting_credentials(monkeypatch):
    monkeypatch.setenv("GMAIL_CLIENT_SECRET", "synthetic-do-not-inherit")
    original = asyncio.create_subprocess_exec
    seen = []

    async def spawn(*args, **kwargs):
        seen.append(kwargs["env"])
        return await original(*args, **kwargs)
    monkeypatch.setattr(document_processing.asyncio, "create_subprocess_exec", spawn)
    result = asyncio.run(document_processing.parse_resume_isolated(b"Synthetic Candidate\ncandidate@example.invalid\nPython SQL", "untrusted filename.txt"))
    assert "candidate@example.invalid" in str(result)
    assert seen and "GMAIL_CLIENT_SECRET" not in seen[0] and "DATABASE_URL" not in seen[0]


def test_resume_timeout_kills_child_and_releases_capacity(monkeypatch):
    import sys
    original = asyncio.create_subprocess_exec
    children = []
    monkeypatch.setattr(document_processing, "PARSER_TIMEOUT_SECONDS", .1)

    async def spawn(*args, **kwargs):
        process = await original(sys.executable, "-c", "import time; time.sleep(60)", **kwargs)
        children.append(process)
        return process
    monkeypatch.setattr(document_processing.asyncio, "create_subprocess_exec", spawn)

    async def scenario():
        for _ in range(3):
            with pytest.raises(ValueError, match="safety budget"):
                await document_processing.parse_resume_isolated(b"Synthetic", "resume.txt")
            assert children[-1].returncode is not None
    asyncio.run(scenario())


def test_body_budget_rejects_advertised_or_streamed_oversize_and_slow_bodies():
    async def scenario(headers, chunks, *, slow=False):
        sent, called = [], []
        iterator = iter(chunks)

        async def receive():
            if slow:
                await asyncio.sleep(60)
            return next(iterator)

        async def downstream(scope, receive, send):
            called.append(True)
        middleware = BodyLimitMiddleware(downstream, max_bytes=4, timeout_seconds=.02)
        await middleware({"type": "http", "method": "POST", "headers": headers}, receive, lambda message: capture(sent, message))
        return sent, called

    async def capture(sent, message):
        sent.append(message)

    for headers, chunks, slow, expected in [
        ([(b"content-length", b"500")], [], False, 413),
        ([], [{"type": "http.request", "body": b"a", "more_body": True}] * 5, False, 413),
        ([], [], True, 408),
        ([(b"content-length", b"invalid")], [], False, 400),
    ]:
        sent, called = asyncio.run(scenario(headers, chunks, slow=slow))
        assert sent[0]["status"] == expected and not called


def test_production_origin_cannot_be_authorized_by_spoofing_host(monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    monkeypatch.setattr(main.settings, "production", True)
    monkeypatch.setattr(main.settings, "cors_origins", ["https://workspace.example.invalid"])
    monkeypatch.setattr(main.settings, "public_origin", "https://workspace.example.invalid")
    client = TestClient(main.app)
    response = client.post("/api/auth/login", json={}, headers={"Origin": "https://untrusted.example.invalid", "Host": "untrusted.example.invalid"})
    assert response.status_code == 403 and response.json()["detail"] == "Request origin is not allowed"


def test_non_ascii_csrf_is_rejected_without_a_server_error():
    from starlette.requests import Request
    from app.main import current_user
    request = Request({"type": "http", "method": "POST", "headers": [
        (b"cookie", b"internpilot_session=synthetic"), (b"x-csrf-token", "invalid-é".encode())]})
    db = SimpleNamespace(get=lambda *args: SimpleNamespace(expires_at="2099-01-01T00:00:00+00:00", csrf_token="valid-ascii"))
    with pytest.raises(HTTPException) as rejected:
        current_user(request, db)
    assert rejected.value.status_code == 403


def test_parser_cancellation_reaps_children_and_rejects_excess_work(monkeypatch):
    import sys
    original = asyncio.create_subprocess_exec
    children = []

    async def spawn(*args, **kwargs):
        process = await original(sys.executable, "-c", "import time; time.sleep(60)", **kwargs)
        children.append(process)
        return process
    monkeypatch.setattr(document_processing.asyncio, "create_subprocess_exec", spawn)

    async def scenario():
        tasks = [asyncio.create_task(document_processing.parse_resume_isolated(b"Synthetic", "resume.txt")) for _ in range(2)]
        for _ in range(100):
            if len(children) == 2:
                break
            await asyncio.sleep(.01)
        assert len(children) == 2
        with pytest.raises(document_processing.ParserBusyError):
            await document_processing.parse_resume_isolated(b"Synthetic", "resume.txt")
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        assert all(child.returncode is not None for child in children)
    asyncio.run(scenario())


def test_backup_wall_timeout_cleans_incomplete_output(tmp_path):
    import os
    from pathlib import Path
    import subprocess
    import sys
    import time
    from cryptography.fernet import Fernet
    if os.name == "nt":
        pytest.skip("POSIX executable fixture; Windows needs a native pg_dump timeout drill")
    executable = tmp_path / "pg_dump"
    executable.write_text("#!" + sys.executable + "\nimport time\ntime.sleep(60)\n")
    executable.chmod(0o700)
    target = tmp_path / "incomplete.ipbk"
    env = dict(os.environ, DATA_DIR=str(tmp_path), ENCRYPTION_KEY=Fernet.generate_key().decode(), ENCRYPTION_SECRET="",
        ENVIRONMENT="development", DATABASE_URL="postgresql+psycopg://synthetic@127.0.0.1/unused", PATH=str(tmp_path) + os.pathsep + os.environ.get("PATH", ""))
    started = time.perf_counter()
    result = subprocess.run([sys.executable, str(Path(__file__).parents[2] / "scripts/secure-backup.py"), str(target), "--timeout", "1"],
        env=env, capture_output=True, timeout=10, check=False)
    assert result.returncode != 0 and not target.exists() and time.perf_counter() - started < 8


def test_backup_output_error_kills_dump_before_waiting(tmp_path, monkeypatch):
    import importlib.util
    import io
    from pathlib import Path
    import sys
    from app.config import settings
    path = Path(__file__).parents[2] / "scripts/secure-backup.py"
    spec = importlib.util.spec_from_file_location("phase7_backup", path)
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    killed = []

    class Dump:
        stdout = io.BytesIO(b"synthetic")

        def __enter__(self): return self
        def __exit__(self, *args): assert killed
        def kill(self): killed.append(True)

    def broken_output(*args):
        raise OSError("Synthetic full disk")
    monkeypatch.setattr(settings, "database_url", "postgresql+psycopg://synthetic@127.0.0.1/unused")
    monkeypatch.setattr(module.subprocess, "Popen", lambda *args, **kwargs: Dump())
    monkeypatch.setattr(module, "encrypt_stream", broken_output)
    output = tmp_path / "incomplete.ipbk"
    monkeypatch.setattr(sys, "argv", [str(path), str(output)])
    with pytest.raises(OSError, match="Synthetic full disk"):
        module.main()
    assert killed and not output.exists()
