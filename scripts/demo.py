"""Run the real browser demo against a loopback InternPilot TEST_MODE server.

No password argument is accepted. Credentials are read with getpass, retained in
memory for login, and never printed. The server supplies a synthetic candidate;
this client never changes the real candidate profile or invokes external apply.
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
from http.cookiejar import CookieJar
import json
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener


class DemoClient:
    def __init__(self, base_url: str):
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Demo client accepts only a loopback HTTP(S) API URL.")
        if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
            raise ValueError("Supply an API origin without credentials, paths, query or fragment.")
        self.base_url = base_url.rstrip("/")
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))
        self.csrf_token = ""

    def request(self, path: str, payload: dict | None = None, *, binary: bool = False):
        headers = {"Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
            if self.csrf_token:
                headers["X-CSRF-Token"] = self.csrf_token
        request = Request(self.base_url + path, data=json.dumps(payload).encode() if payload is not None else None, headers=headers)
        try:
            with self.opener.open(request, timeout=30) as response:
                content = response.read()
        except HTTPError as exc:
            try:
                detail = json.loads(exc.read(20_000)).get("detail", "Request rejected")
            except (ValueError, AttributeError):
                detail = "Request rejected"
            raise RuntimeError(f"API HTTP {exc.code}: {str(detail)[:500]}") from None
        except URLError:
            raise RuntimeError("The local API is unavailable. Start API and worker first.") from None
        return content if binary else json.loads(content)


def run_demo(client: DemoClient, *, timeout: int = 120, artifacts: Path | None = None) -> dict:
    queued = client.request("/api/demo/run", {})
    application_id = queued["application"]["id"]
    deadline = time.monotonic() + timeout
    state = queued["application"]
    while state["status"] not in {"submitted", "uncertain", "failed", "needs_input", "awaiting_review"}:
        if time.monotonic() >= deadline:
            raise RuntimeError("Timed out waiting for the worker. Inspect application logs; do not force-resubmit.")
        time.sleep(1)
        rows = client.request("/api/applications")
        state = next(row for row in rows if row["id"] == application_id)
    duplicate = client.request("/api/demo/run", {})
    if duplicate["application"]["id"] != application_id or not duplicate.get("duplicate_prevented"):
        raise RuntimeError("Duplicate prevention did not return the original local application.")
    result = {"application_id": application_id, "status": state["status"], "confirmation_id": state.get("confirmation_id"), "duplicate_prevented": True, "local_test_only": True}
    if state["status"] == "submitted" and state.get("confirmation_id"):
        resume = client.request(f"/api/documents/{state['document_id']}/download", binary=True)
        receipt = client.request("/test-portal/records/" + quote(state["confirmation_id"], safe=""))
        if receipt["resume_sha256"] != hashlib.sha256(resume).hexdigest() or receipt["resume_bytes"] != len(resume):
            raise RuntimeError("The local test portal's uploaded-document hash did not match the generated PDF.")
        result["uploaded_resume_verified"] = True
    if artifacts:
        artifacts.mkdir(parents=True, exist_ok=True)
        for key, name in (("document_id", "local-demo-resume.pdf"), ("screenshot_id", "local-demo-before-submit.png")):
            if state.get(key):
                content = client.request(f"/api/documents/{state[key]}/download", binary=True)
                (artifacts / name).write_bytes(content)
        (artifacts / "local-demo-result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if state["status"] != "submitted" or not state.get("confirmation_id"):
        raise RuntimeError(f"Local demo ended in {state['status']}: {state.get('reason', 'Inspect the application queue')}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--email", required=True, help="Account for this local test. No email is sent.")
    parser.add_argument("--register", action="store_true", help="Create a new dedicated test account.")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--artifacts", type=Path)
    args = parser.parse_args()
    try:
        client = DemoClient(args.base_url)
        health = client.request("/api/health")
        if health.get("test_mode") is not True:
            raise RuntimeError("The API is not in TEST_MODE. Enable it explicitly for an isolated local demonstration.")
        password = getpass.getpass("Test account password (at least 12 characters): ")
        if args.register and password != getpass.getpass("Confirm test account password: "):
            raise ValueError("Passwords did not match.")
        session = client.request("/api/auth/register" if args.register else "/api/auth/login", {"email": args.email, "password": password})
        password = ""
        client.csrf_token = session["csrf_token"]
        result = run_demo(client, timeout=max(10, min(args.timeout, 600)), artifacts=args.artifacts)
        print(json.dumps(result, indent=2))
        client.request("/api/auth/logout", {})
        return 0
    except (ValueError, RuntimeError, KeyError, StopIteration) as exc:
        print(f"Demo stopped: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
