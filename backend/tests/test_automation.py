"""Actual browser acceptance tests: only the local authorized test portal is used."""
from __future__ import annotations

import asyncio
import hashlib
import os
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from app.automation import _origin, _public_target, run_application

PDF = b"%PDF-1.4\n% InternPilot synthetic browser fixture\n%%EOF\n"
PROFILE = {
    "name": "Synthetic Test Candidate", "email": "synthetic-test@example.invalid",
    "country": "India", "graduation_year": 2029,
    "verified_fields": ["name", "email", "country", "graduation_year"],
}


@pytest.fixture(scope="module")
def portal(tmp_path_factory):
    directory = tmp_path_factory.mktemp("browser-portal")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"
    env = {**os.environ, "DATA_DIR": str(directory)}
    logfile = (directory / "server.log").open("w+")
    script = (
        "from fastapi import FastAPI; from app.test_portal import router; "
        "import uvicorn; app=FastAPI(); app.include_router(router); "
        f"uvicorn.run(app,host='127.0.0.1',port={port},log_level='error')"
    )
    process = subprocess.Popen([sys.executable, "-c", script], cwd=Path(__file__).parents[1], env=env, stdout=logfile, stderr=logfile)
    try:
        for _ in range(100):
            if process.poll() is not None:
                logfile.seek(0)
                pytest.fail(f"Test portal failed: {logfile.read()}")
            try:
                with httpx.Client(trust_env=False) as client:
                    if client.get(origin + "/test-portal/apply").status_code == 200:
                        break
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        else:
            pytest.fail("Test portal did not become ready")
        yield origin, directory
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        logfile.close()


@pytest.fixture
def application_kwargs(portal, monkeypatch):
    origin, _ = portal
    monkeypatch.setenv("TEST_PORTAL_ORIGIN", origin)
    return dict(
        url=origin + "/test-portal/apply", profile=PROFILE, resume=PDF,
        submit=False, approved=False, allowed_origins=[origin], test_mode=True,
    )


def test_exact_origins_and_private_targets():
    assert _origin("https://example.com:443/a") == "https://example.com"
    for url in ("file:///etc/passwd", "https://a:b@example.com", "http://127.0.0.1:80/#secret"):
        with pytest.raises(ValueError):
            _origin(url)
    with pytest.raises(ValueError, match="HTTPS"):
        asyncio.run(_public_target("http://example.com/apply", {"http://example.com"}, test_origin=None))
    with pytest.raises(ValueError, match="Private"):
        asyncio.run(_public_target("https://127.0.0.1/apply", {"https://127.0.0.1"}, test_origin=None))
    with pytest.raises(ValueError, match="Private"):
        asyncio.run(_public_target("https://169.254.169.254/latest", {"https://169.254.169.254"}, test_origin=None))


def test_local_mode_never_allows_general_loopback(application_kwargs):
    application_kwargs["url"] = application_kwargs["url"].replace("/test-portal/apply", "/api/profile")
    result = asyncio.run(run_application(**application_kwargs))
    assert result["status"] == "needs_input"
    assert "isolated" in result["reason"]


def test_test_mode_cannot_be_repointed_to_external_origin(application_kwargs, monkeypatch):
    monkeypatch.setenv("TEST_PORTAL_ORIGIN", "https://example.com")
    result = asyncio.run(run_application(**application_kwargs))
    assert result["status"] == "needs_input"
    assert "loopback" in result["reason"]


def test_unapproved_submit_is_blocked_before_browser(application_kwargs):
    application_kwargs["submit"] = True
    result = asyncio.run(run_application(**application_kwargs))
    assert result["status"] == "needs_input"
    assert result["screenshot"] is None
    assert "approval" in result["reason"]


def test_external_submission_has_no_certified_adapter(monkeypatch):
    # No real request is made: public literal address is checked, then unsupported
    # employer submission is rejected before browser launch.
    result = asyncio.run(run_application(
        url="https://8.8.8.8/apply", profile=PROFILE, resume=PDF,
        submit=True, approved=True, allowed_origins=["https://8.8.8.8"],
    ))
    assert result["status"] == "needs_input"
    assert "no certified submission adapter" in result["reason"]


def test_assisted_fills_uploads_and_captures_without_submission(application_kwargs, portal):
    result = asyncio.run(run_application(**application_kwargs))
    assert result["status"] == "awaiting_review", result["reason"]
    assert result["screenshot"].startswith(b"\x89PNG")
    assert result["confirmation_id"] is None
    assert len(result["fields"]) == 5
    assert all(f["status"] == "filled" for f in result["fields"])
    assert all("value" not in f for f in result["fields"])
    _, directory = portal
    if (directory / "test-portal.sqlite3").exists():
        with sqlite3.connect(directory / "test-portal.sqlite3") as db:
            assert db.execute("SELECT count(*) FROM submissions").fetchone()[0] == 0


def test_missing_verified_fact_pauses(application_kwargs):
    application_kwargs["profile"] = {**PROFILE, "verified_fields": ["name", "country", "graduation_year"]}
    result = asyncio.run(run_application(**application_kwargs))
    assert result["status"] == "needs_input"
    assert any(f["status"] == "human_required" for f in result["fields"])
    assert result["confirmation_id"] is None


def test_sensitive_question_pauses_before_submission(application_kwargs):
    application_kwargs.update(url=application_kwargs["url"] + "?variant=ambiguous", submit=True, approved=True)
    called = []
    application_kwargs["before_submit"] = lambda screenshot: called.append(True)
    result = asyncio.run(run_application(**application_kwargs))
    assert result["status"] == "needs_input"
    assert "sensitive" in result["reason"]
    assert not called
    assert result["screenshot"].startswith(b"\x89PNG")


def test_captcha_pauses(application_kwargs):
    application_kwargs["url"] += "?variant=captcha"
    result = asyncio.run(run_application(**application_kwargs))
    assert result["status"] == "needs_input"
    assert "CAPTCHA" in result["reason"]


def test_final_policy_recheck_blocks(application_kwargs):
    screenshots = []

    async def stop(screenshot):
        screenshots.append(screenshot)
        return False

    application_kwargs.update(submit=True, approved=True, before_submit=stop)
    result = asyncio.run(run_application(**application_kwargs))
    assert result["status"] == "needs_input"
    assert "policy" in result["reason"]
    assert screenshots[0].startswith(b"\x89PNG")
    assert result["confirmation_id"] is None


def test_submit_confirmation_upload_and_idempotency(application_kwargs, portal):
    calls = []

    async def allow(screenshot):
        assert screenshot.startswith(b"\x89PNG")
        calls.append("durable_before_click")
        return True

    application_kwargs.update(submit=True, approved=True, before_submit=allow)
    result = asyncio.run(run_application(**application_kwargs))
    assert result["status"] == "submitted", result["reason"]
    assert result["confirmation_id"].startswith("TEST-")
    assert calls == ["durable_before_click"]
    origin, _ = portal
    with httpx.Client(trust_env=False) as client:
        record = client.get(f'{origin}/test-portal/records/{result["confirmation_id"]}').json()
    assert record["resume_sha256"] == hashlib.sha256(PDF).hexdigest()
    assert record["resume_bytes"] == len(PDF)
    # The authorized fixture also deduplicates independently of the application
    # database; retrying the same requisition+candidate returns the same receipt.
    again = asyncio.run(run_application(**application_kwargs))
    assert again["confirmation_id"] == result["confirmation_id"]


def test_missing_confirmation_is_uncertain_not_success(application_kwargs):
    application_kwargs.update(
        url=application_kwargs["url"] + "?variant=no-confirmation", submit=True, approved=True,
        profile={**PROFILE, "email": "uncertain-outcome@example.invalid"}, before_submit=lambda screenshot: True,
    )
    result = asyncio.run(run_application(**application_kwargs))
    assert result["status"] == "uncertain"
    assert result["confirmation_id"] is None
    assert "do not retry" in result["reason"]


def test_uncertified_static_form_prepares_but_requires_manual_completion(application_kwargs, monkeypatch):
    # Exercise the external static-HTML branch against the local fixture only.
    # No public employer endpoint is contacted and the production guard is not
    # relaxed: this monkeypatch lives solely in this test process.
    import app.automation as automation
    origin = application_kwargs["allowed_origins"][0]

    async def allow_fixture_only(url, allowed, *, test_origin):
        assert url.startswith(origin + "/test-portal/")
        assert origin in allowed

    monkeypatch.setattr(automation, "_public_target", allow_fixture_only)
    # This fixture is loopback-only even though it exercises the external-form
    # branch. Root/container CI cannot run Chromium's OS sandbox. Intercept only
    # this test's launch, assert production requested a sandbox, then run the
    # isolated local fixture without one. Production code has no such fallback;
    # the next test verifies sandbox failures stop external preparation.
    from playwright.async_api import BrowserType
    real_launch = BrowserType.launch

    async def local_fixture_launch(browser_type, **options):
        assert options["chromium_sandbox"] is True
        assert "--no-sandbox" not in options.get("args", [])
        return await real_launch(browser_type, **{**options, "chromium_sandbox": False, "args": ["--no-sandbox"]})

    monkeypatch.setattr(BrowserType, "launch", local_fixture_launch)
    application_kwargs["test_mode"] = False
    application_kwargs["before_upload"] = lambda: True  # Specific synthetic fixture approval.
    result = asyncio.run(run_application(**application_kwargs))
    assert result["status"] == "needs_input"
    assert "manual completion" in result["reason"]
    assert all(f["status"] == "filled" for f in result["fields"])
    assert result["screenshot"].startswith(b"\x89PNG")
    assert result["confirmation_id"] is None


def test_external_sandbox_failure_never_falls_back_to_unsafe_launch(monkeypatch):
    import app.automation as automation
    launches = []

    class Chromium:
        async def launch(self, **options):
            launches.append(options)
            raise automation.PlaywrightError("Required browser sandbox is unavailable")

    class PlaywrightContext:
        chromium = Chromium()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    monkeypatch.setattr(automation, "async_playwright", PlaywrightContext)
    # A global unsafe flag must not override the external-page safety policy.
    monkeypatch.setenv("PLAYWRIGHT_NO_SANDBOX", "true")
    result = asyncio.run(run_application(
        url="https://8.8.8.8/apply", profile=PROFILE, resume=PDF,
        submit=False, approved=False, allowed_origins=["https://8.8.8.8"], before_upload=lambda: True,
    ))
    assert len(launches) == 1
    assert launches[0]["chromium_sandbox"] is True
    assert "--no-sandbox" not in launches[0].get("args", [])
    assert result["status"] == "needs_input"
    assert result["confirmation_id"] is None
