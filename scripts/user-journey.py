"""Real browser + application worker journey, restricted to isolated local data."""
import hashlib
import json
import os
import secrets
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
assert os.environ.get("UI_TEST_ALLOW_OWNER_CLI") == "true"
assert "internpilot-ui-" in os.environ.get("DATABASE_URL", "")
assert os.environ.get("TEST_MODE") == "true"
assert os.environ.get("WORKER_KINDS") == "application"
BASE = os.environ["UI_TEST_URL"]
OUT = Path(os.getenv("UI_ARTIFACT_DIR", str(ROOT / "artifacts/user-check/journey")))
OUT.mkdir(parents=True, exist_ok=True)
report = {"at": datetime.now(UTC).isoformat(), "synthetic_only": True,
          "external_submissions": 0, "external_emails": 0, "checks": []}


def check(name):
    report["checks"].append({"name": name, "passed": True})
    print(name + ": passed", flush=True)


with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=shutil.which("chromium"),
                                 headless=True, args=["--no-sandbox"])
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = context.new_page()
    page.set_default_timeout(25000)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        email, password = f"journey-{secrets.token_hex(6)}@example.invalid", secrets.token_urlsafe(24)
        page.goto(BASE + "/register")
        page.get_by_label("Email address", exact=True).fill(email)
        page.get_by_label("Password", exact=False).fill(password)
        page.get_by_role("button", name="Create your workspace", exact=True).click()
        expect(page.get_by_role("heading", name="A clearer next step.", exact=True)).to_be_visible()
        expect(page.get_by_text("This view couldn’t load.", exact=True)).to_have_count(0)
        check("Fresh account overview loads without a catalog-indexing error")

        page.goto(BASE + "/applications")
        expect(page.get_by_role("heading", name="Your application journey starts here")).to_be_visible()
        check("Fresh account shows an honest empty application history")

        # Trigger a genuine read failure, then recover through the visible control.
        def unavailable(route):
            route.fulfill(status=503, content_type="application/json",
                          body=json.dumps({"detail": "Local QA: API temporarily unavailable"}))

        page.route("**/api/v2/opportunities?*", unavailable)
        page.goto(BASE + "/explore/internships")
        expect(page.get_by_role("button", name="Try again", exact=True)).to_be_visible()
        page.screenshot(path=str(OUT / "api-failure.png"))
        page.unroute("**/api/v2/opportunities?*", unavailable)
        page.get_by_role("button", name="Try again", exact=True).click()
        expect(page.get_by_role("button", name="Try again", exact=True)).to_have_count(0)
        check("API outage presents a retry state and recovers without logout")

        report["stream_probe"] = page.evaluate("""async () => {
          const controller = new AbortController();
          const timer = setTimeout(() => controller.abort(), 5000);
          const start = performance.now();
          let reader;
          try {
            const response = await fetch('/api/events/stream', {signal: controller.signal});
            reader = response.body.getReader();
            const first = await reader.read();
            return {ready: new TextDecoder().decode(first.value).includes('event: ready'),
              seconds: (performance.now() - start) / 1000,
              encoding: response.headers.get('content-encoding'),
              cache_control: response.headers.get('cache-control')};
          } catch (error) {return {ready: false, error: error.name};}
          finally {clearTimeout(timer); controller.abort(); if (reader) await reader.cancel().catch(() => {});}
        }""")
        print("Stream probe: " + json.dumps(report["stream_probe"]), flush=True)
        assert report["stream_probe"]["ready"], report["stream_probe"]
        check("Event stream delivers its ready event through the frontend proxy without buffering")

        # This visible action explicitly authorizes synthetic submission locally.
        page.goto(BASE + "/automation/policies")
        submitted_at = time.monotonic()
        with page.expect_response(lambda r: r.url.endswith("/api/demo/run") and r.request.method == "POST") as pending:
            page.get_by_role("button", name="Run local application test", exact=True).click()
        response = pending.value
        assert response.status == 200, response.text()
        application_id = response.json()["application"]["id"]
        page.goto(BASE + "/applications")
        # Wait on UI updates from the actual worker, not manual client invalidation.
        entry = page.locator(".kanban-entry").filter(has_text="LOCAL TEST")
        expect(entry).to_have_count(1)
        expect(entry).to_contain_text("Confirmation: TEST-", timeout=90000)
        expect(entry).to_contain_text("submitted")
        report["click_to_visible_confirmation_seconds"] = round(time.monotonic() - submitted_at, 3)
        entry.click()
        dialog = page.get_by_role("dialog", name="Application record")
        expect(dialog).to_be_visible()
        page.screenshot(path=str(OUT / "confirmed-application.png"))
        check("Worker fills the local form, uploads PDF, confirms submission and updates the pipeline")

        applications = context.request.get(BASE + "/api/applications").json()
        assert len(applications) == 1
        application = applications[0]
        assert application["id"] == application_id and application["status"] == "submitted"
        confirmation = application["confirmation_id"]
        pdf = context.request.get(BASE + f'/api/documents/{application["document_id"]}/download')
        screenshot = context.request.get(BASE + f'/api/documents/{application["screenshot_id"]}/download')
        assert pdf.status == 200 and pdf.body().startswith(b"%PDF-")
        assert screenshot.status == 200 and screenshot.body().startswith(b"\x89PNG")
        receipt = context.request.get("http://127.0.0.1:8000/test-portal/records/" + confirmation).json()
        assert receipt["resume_sha256"] == hashlib.sha256(pdf.body()).hexdigest()
        report["confirmed_local_submission"] = True
        report["uploaded_pdf_bytes"] = len(pdf.body())
        check("Downloaded resume matches the test portal's actual uploaded document hash")

        page.keyboard.press("Escape")
        page.goto(BASE + "/automation/policies")
        with page.expect_response(lambda r: r.url.endswith("/api/demo/run") and r.request.method == "POST") as pending:
            page.get_by_role("button", name="Run local application test", exact=True).click()
        repeated = pending.value.json()
        assert repeated["duplicate_prevented"] and repeated["application"]["id"] == application_id
        assert len(context.request.get(BASE + "/api/applications").json()) == 1
        check("Repeating the action returns the same application without duplicate submission")

        page.reload()
        page.goto(BASE + "/applications")
        expect(page.locator(".kanban-entry")).to_have_count(1)
        expect(page.locator(".kanban-entry")).to_contain_text(confirmation)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(OUT / "pipeline-mobile.png"))
        check("Confirmed application survives refresh and mobile pipeline does not overflow")

        # A valid cookie plus a temporary auth-service failure is not a logout.
        page.route("**/api/auth/session", unavailable)
        page.reload()
        expect(page.get_by_role("heading", name="We couldn’t check your session.", exact=True)).to_be_visible()
        assert "/applications" in page.url
        page.screenshot(path=str(OUT / "session-outage.png"))
        page.unroute("**/api/auth/session", unavailable)
        page.get_by_role("button", name="Try again", exact=True).click()
        expect(page.locator(".kanban-entry")).to_contain_text(confirmation)
        check("Session-service outage retains the URL and recovers the existing session through Retry")

        page.set_viewport_size({"width": 1440, "height": 1000})
        page.get_by_role("button", name="Sign out", exact=True).click()
        expect(page.get_by_role("button", name="Sign in", exact=True)).to_be_visible()
        assert context.request.get(BASE + "/api/profile").status == 401
        page.goto(BASE + "/applications")
        expect(page.get_by_role("button", name="Sign in", exact=True)).to_be_visible()
        page.get_by_label("Email address", exact=True).fill(email)
        page.get_by_label("Password", exact=True).fill(password + "incorrect")
        page.get_by_role("button", name="Sign in", exact=True).click()
        expect(page.get_by_role("alert").filter(has_text="Invalid email or password")).to_be_visible()
        page.get_by_label("Password", exact=True).fill(password)
        page.get_by_role("button", name="Sign in", exact=True).click()
        expect(page.get_by_role("heading", name="A clearer next step.", exact=True)).to_be_visible()
        page.goto(BASE + "/applications")
        expect(page.locator(".kanban-entry")).to_contain_text(confirmation)
        check("Logout revokes access; wrong-password login fails and valid login restores saved work")
        assert not errors, errors
        report["javascript_errors"] = errors
        report["passed"] = True
    except Exception as exc:
        report["passed"] = False
        report["failure"] = str(exc)
        report["javascript_errors"] = errors
        page.screenshot(path=str(OUT / "failure.png"))
        print(page.locator("body").inner_text()[:5000], flush=True)
        raise
    finally:
        (OUT / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        browser.close()
