"""Browser acceptance against a running local frontend + isolated test backend.

Run: backend/.venv/bin/python scripts/ui_acceptance.py
Only synthetic profile data is entered. No external application is submitted.
Discovery, if enabled, performs permitted public read-only requests.
"""
import json
import os
import re
import secrets
import shutil
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts"
BASE = os.getenv("UI_TEST_URL", "http://127.0.0.1:3000")
if urlsplit(BASE).hostname not in {"localhost", "127.0.0.1"}:
    raise SystemExit("UI acceptance requires an isolated local test environment")
OUT.mkdir(exist_ok=True)
report = {"frontend": BASE, "checks": [], "external_submissions": 0}

def report_failure(exc_type, exc, traceback):
    report["passed"] = False
    report["failure"] = f"{exc_type.__name__}: {str(exc)[:1500]}"
    (OUT / "ui-acceptance.json").write_text(json.dumps(report, indent=2))
    sys.__excepthook__(exc_type, exc, traceback)

sys.excepthook = report_failure

def passed(name):
    report["checks"].append({"name": name, "passed": True})
    print(name + ": passed", flush=True)

with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE") or shutil.which("chromium"), headless=True, args=["--no-sandbox"])
    context = browser.new_context(viewport={"width": 1440, "height": 1050}, accept_downloads=True)
    page = context.new_page()
    page.set_default_timeout(20000)
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(BASE, wait_until="domcontentloaded", timeout=60000)
    health = context.request.get(BASE + "/api/health").json()
    assert health.get("test_mode"), "Refusing demo on a backend without test_mode"
    page.get_by_label("Email address", exact=True).fill("browser-" + secrets.token_hex(6) + "@example.test")
    password = secrets.token_urlsafe(24)
    page.get_by_label("Password", exact=False).fill(password)
    page.get_by_role("button", name="Create your workspace", exact=True).click()
    page.get_by_role("heading", name="Your search, in focus.").wait_for()
    passed("UI registration and authenticated dashboard")
    page.get_by_role("button", name="Candidate profile", exact=True).click()
    for label, value in [("Full name", "Synthetic UI Candidate"), ("Application email", "synthetic-candidate@example.test"), ("Phone number", "+919999999999"), ("University / institution", "Synthetic Test University"), ("Degree / program", "B.Tech Computer Science"), ("Verified technical skills", "Python, TypeScript, Git")]:
        page.get_by_label(label, exact=False).fill(value)
        group = page.locator(".verified-field").filter(has=page.get_by_label(label, exact=False))
        group.get_by_role("checkbox").check()
    page.get_by_role("button", name="Save verified profile", exact=True).click()
    page.get_by_role("status").filter(has_text="Profile saved").wait_for()
    facts = context.request.get(BASE + "/api/profile").json()
    assert facts["name"] == "Synthetic UI Candidate"
    assert facts["skills"] == ["Python", "TypeScript", "Git"]
    assert "skills" in facts["verified_fields"]
    passed("Profile editing, comma-separated skills, explicit verification and persistence")
    page.get_by_role("button", name="Application policies", exact=True).click()
    page.get_by_text("Assisted Apply", exact=True).click()
    page.get_by_role("button", name="Save application policies", exact=True).click()
    page.get_by_role("status").filter(has_text="Application policies saved").wait_for()
    policy = context.request.get(BASE + "/api/policy").json()
    assert policy["mode"] == "assisted" and policy["auto_consent"] is False
    passed("Assisted mode saved; Auto Apply remains inactive")
    page.get_by_role("button", name="Discovery sources", exact=True).click()
    page.get_by_role("heading", name="Configured sources").wait_for()
    assert page.locator(".source-row").count() > 0
    passed("Actual configured source health renders")
    page.get_by_role("button", name="Overview", exact=True).click()
    page.screenshot(path=str(OUT / "dashboard-desktop.png"), full_page=True)
    page.get_by_role("button", name="Application policies", exact=True).click()
    page.get_by_role("button", name="Run local application test", exact=True).click()
    deadline = time.monotonic() + 75
    local = None
    while time.monotonic() < deadline:
        rows = context.request.get(BASE + "/api/applications").json()
        local = next((a for a in rows if a.get("is_demo")), None)
        if local and local["status"] in {"submitted", "failed", "needs_input", "uncertain"}:
            break
        page.wait_for_timeout(1500)
    assert local and local["status"] == "submitted", str(local)
    assert local["confirmation_id"] and local["screenshot_id"] and local["document_id"]
    passed("Local browser demo confirms upload, submission, screenshot and confirmation")
    page.get_by_role("button", name="Run local application test", exact=True).click()
    page.get_by_role("status").filter(has_text="Local test").wait_for()
    demo_rows = [a for a in context.request.get(BASE + "/api/applications").json() if a.get("is_demo")]
    assert len(demo_rows) == 1 and demo_rows[0]["confirmation_id"] == local["confirmation_id"]
    passed("Repeated local demo action preserves the same application and receipt")
    page.get_by_role("button", name="Applications", exact=True).click()
    page.get_by_text("LOCAL TEST", exact=True).first.wait_for()
    page.get_by_text("Confirmation:", exact=False).wait_for()
    passed("Application list labels synthetic test and displays authoritative confirmation")
    page.get_by_role("button", name="Documents", exact=True).click()
    with page.expect_download() as d:
        page.get_by_role("link", name="Download", exact=True).filter(has_text="Download").first.click()
    download = d.value
    download.save_as(OUT / ("ui-" + download.suggested_filename))
    passed("Authenticated document download")
    page.get_by_role("button",name="Discovery sources",exact=True).click()
    synthetic = [{"title":f"Software Engineering Intern — SYNTHETIC UI {index:02d}",
                  "company":"Local Acceptance Fixture","job_url":f"https://acceptance.example.invalid/intern/{index}",
                  "location":"India","is_remote":index%2==0,"compensation":"INR 10000 / month" if index%2==0 else None,"description":"Local synthetic metadata fixture; Python."} for index in range(25)]
    page.get_by_label("Opportunity export file").set_input_files({"name":"synthetic-jobs.json","mimeType":"application/json","buffer":json.dumps(synthetic).encode()})
    page.get_by_role("button",name="Import opportunities",exact=True).click()
    page.get_by_role("status").filter(has_text="25 new references").wait_for()
    page.get_by_role("button",name="Import opportunities",exact=True).click()
    page.get_by_role("status").filter(has_text="0 new references").wait_for()
    passed("JobSpy-format import works in UI and a repeated import deduplicates")
    page.get_by_role("button",name="Internship explorer",exact=True).click()
    page.get_by_label("Search opportunities",exact=True).fill("SYNTHETIC UI")
    expect(page.locator(".results-bar strong")).to_have_text("25")
    page.get_by_text("Page 1 of 2",exact=True).wait_for()
    page.get_by_role("button",name="Next",exact=True).click()
    page.get_by_text("Page 2 of 2",exact=True).wait_for()
    expect(page.locator(".job-card")).to_have_count(5)
    page.get_by_role("button",name="Filters",exact=True).click()
    page.get_by_label("Paid internships / disclosed cash prizes",exact=True).check()
    expect(page.locator(".results-bar strong")).to_have_text("13")
    expect(page.locator(".job-card")).to_have_count(13)
    page.get_by_label("Paid internships / disclosed cash prizes",exact=True).uncheck()
    expect(page.locator(".results-bar strong")).to_have_text("25")
    passed("Paid-opportunity filter excludes unknown compensation and updates pagination")
    page.get_by_role("button",name=re.compile(r"^Save Software Engineering Intern — SYNTHETIC UI")).first.click()
    page.get_by_role("button",name=re.compile(r"^Unsave Software Engineering Intern — SYNTHETIC UI")).first.wait_for()
    page.get_by_role("button",name="Saved opportunities",exact=True).click()
    page.locator(".job-card").first.wait_for()
    assert page.locator(".job-card").count()==1
    page.locator(".job-card").first.click()
    page.get_by_role("dialog").wait_for()
    page.get_by_role("button",name="Close dialog",exact=True).click()
    passed("Explorer search, pagination, bookmark and saved detail workflows")
    page.get_by_label("Color theme").select_option("dark")
    assert page.evaluate("document.documentElement.dataset.theme")=="dark"
    page.reload(wait_until="domcontentloaded")
    page.get_by_role("button",name="Saved opportunities",exact=True).click()
    page.locator(".job-card").first.wait_for()
    assert page.evaluate("document.documentElement.dataset.theme")=="dark"
    assert page.locator(".job-card").count()==1
    page.screenshot(path=str(OUT/"saved-dark-desktop.png"),full_page=True)
    page.get_by_label("Color theme").select_option("light")
    passed("Saved opportunities and dark theme persist after page reload")
    page.get_by_role("button",name="Hackathon explorer",exact=True).click()
    page.get_by_role("heading",name="Your next challenge awaits.",exact=True).wait_for()
    page.get_by_role("button",name="Recommended",exact=True).click()
    page.get_by_role("heading",name="Recommended for your next move.",exact=True).wait_for()
    passed("Dedicated hackathon and recommendation views load without replacing internship view")
    page.get_by_role("button",name="Notifications",exact=True).click()
    page.get_by_label("Enable quiet hours",exact=True).check()
    page.get_by_role("button",name="Save notification preferences",exact=True).click()
    page.get_by_role("status").filter(has_text="Notification preferences saved").wait_for()
    assert context.request.get(BASE+"/api/notification-settings").json()["quiet_hours_enabled"]
    assert page.get_by_label("Email delivery",exact=True).is_disabled()
    passed("Quiet hours save and unconfigured outbound provider controls stay unavailable")
    page.get_by_role("button",name="Account security",exact=True).click()
    page.get_by_label("Current password",exact=True).fill(password)
    new_password = secrets.token_urlsafe(24)
    page.get_by_label("New password",exact=True).fill(new_password)
    page.get_by_label("Confirm new password",exact=True).fill(new_password)
    page.get_by_role("button",name="Update password",exact=True).click()
    page.get_by_role("status").filter(has_text="Password updated").wait_for()
    assert context.request.get(BASE+"/api/profile").status==200
    passed("Password rotation renews the active browser session")
    page.get_by_role("button", name="Overview", exact=True).click()
    page.get_by_role("button", name="Find opportunities", exact=True).click()
    deadline = time.monotonic() + 70
    jobs = []
    while time.monotonic() < deadline:
        jobs = context.request.get(BASE + "/api/opportunities").json()
        real = [j for j in jobs if not j.get("is_demo") and j.get("company")!="Local Acceptance Fixture"]
        if real:
            report["real_opportunities_discovered"] = len(real)
            break
        page.wait_for_timeout(2000)
    if report.get("real_opportunities_discovered"):
        passed("UI discovery action retrieves real permitted public listings")
    else:
        report["checks"].append({"name": "UI discovery public network result", "passed": False, "reason": "No real source result within local test deadline; inspect source errors"})
    page.get_by_role("button", name="Overview", exact=True).click()
    page.wait_for_timeout(1500)
    dashboard = context.request.get(BASE + "/api/dashboard").json()
    assert dashboard["metrics"]["submitted"] == 0, "Demo must not inflate real application metrics"
    assert "Confirmed submitted" in page.locator(".pipeline").inner_text()
    assert page.locator(".pipeline-row").filter(has_text="Confirmed submitted").locator("strong").inner_text() == "0"
    passed("Real application metrics and pulse exclude synthetic submissions")
    page.screenshot(path=str(OUT / "dashboard-desktop.png"), full_page=True)
    page.get_by_role("button", name="Internship explorer", exact=True).click()
    page.locator(".job-card").first.wait_for()
    if page.locator(".job-card").count():
        page.locator(".job-card").first.click()
        page.get_by_role("dialog").wait_for()
        page.get_by_role("button", name="Close dialog", exact=True).click()
        passed("Opportunity detail dialog opens and closes")
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_timeout(600)
    overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
    assert not overflow, "Mobile viewport has horizontal overflow"
    page.get_by_role("button", name="Open navigation", exact=True).click()
    page.get_by_role("button", name="Overview", exact=True).click()
    page.wait_for_timeout(400)
    page.screenshot(path=str(OUT / "dashboard-mobile.png"), full_page=True)
    passed("Responsive mobile layout and navigation without horizontal overflow")
    assert not errors, json.dumps(errors)
    passed("No unhandled browser runtime errors")
    browser.close()
report["passed"] = all(x["passed"] for x in report["checks"])
(OUT / "ui-acceptance.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
raise SystemExit(0 if report["passed"] else 1)
