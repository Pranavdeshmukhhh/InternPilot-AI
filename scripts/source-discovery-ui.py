"""Responsive source-review acceptance against fresh synthetic local data only."""
import json
import os
import secrets
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
if os.getenv("UI_TEST_ALLOW_OWNER_CLI") != "true" or "internpilot-ui-" not in os.getenv("DATABASE_URL", ""):
    raise SystemExit("Run through run-ui-acceptance.py --source-discovery-ui with a fresh temporary database")
sys.path.insert(0, str(ROOT / "backend"))
from app.database import SessionLocal
from app.models import Source
from app.publisher_discovery import source_candidate

OUT = ROOT / "artifacts"
report = {"at": datetime.now(UTC).isoformat(), "synthetic_data_only": True, "checks": [],
          "external_emails": 0, "external_submissions": 0, "live_searches": 0, "crawl_workers": 0}


def checked(name):
    report["checks"].append({"name": name, "passed": True})
    print(name + ": passed", flush=True)


try:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=shutil.which("chromium"), headless=True, args=["--no-sandbox"])
        context = browser.new_context(viewport={"width": 1440, "height": 1050})
        page = context.new_page(); page.set_default_timeout(20000)
        errors = []; page.on("pageerror", lambda error: errors.append(str(error)))
        base = os.getenv("UI_TEST_URL", "http://127.0.0.1:3000")
        page.goto(base)
        assert context.request.get(base + "/api/health").json()["test_mode"]
        page.get_by_label("Email address", exact=True).fill("source-review-" + secrets.token_hex(5) + "@example.test")
        page.get_by_label("Password", exact=False).fill(secrets.token_urlsafe(24))
        page.get_by_role("button", name="Create your workspace", exact=True).click()
        page.get_by_role("heading", name="Your opportunity notebook.").wait_for()
        session = context.request.get(base + "/api/auth/session").json()
        board = source_candidate("https://jobs.ashbyhq.com/synthetic-small-browser", "SYNTHETIC small employer", "https://example.com/careers")
        announcement = source_candidate("https://example.com/research/student-program", "SYNTHETIC university program", "https://example.com/careers")
        assert board and announcement
        with SessionLocal() as db:
            parent = Source(owner_id=session["user"]["id"], kind="search", slug="synthetic offline search", company="SYNTHETIC offline fixture",
                            enabled=False, permitted=False, cache={"source_candidates": [board, announcement]})
            db.add(parent); db.commit()
        page.get_by_role("button", name="Internship explorer", exact=True).click()
        page.get_by_text("Local places & discovery coverage", exact=True).click()
        page.get_by_text("New employer & program sources", exact=False).click()
        expect(page.get_by_text("SYNTHETIC small employer", exact=True)).to_be_visible()
        expect(page.get_by_text("SYNTHETIC university program", exact=True)).to_be_visible()
        panel = page.locator("details").filter(has=page.locator("summary").filter(has_text="New employer & program sources")).last
        expect(panel.get_by_text("unverified", exact=False).first).to_be_visible()
        expect(panel.get_by_role("button", name="Enable source", exact=True).first).to_be_disabled()
        checked("Persisted synthetic suggestions appear as unverified with consent required")
        page.screenshot(path=str(OUT / "source-discovery-desktop.png"), full_page=True)
        for width in (390, 768, 1024):
            page.set_viewport_size({"width": width, "height": 900})
            assert page.evaluate("document.documentElement.scrollWidth<=window.innerWidth"), f"Expanded source review overflows at {width}px"
            for button in panel.get_by_role("button", name="Enable source", exact=True).all():
                assert button.bounding_box()["height"] <= 48, f"Source action stretches vertically at {width}px"
            if width == 390:
                page.get_by_label("Color theme", exact=True).select_option("dark")
                page.wait_for_timeout(250)
                panel.scroll_into_view_if_needed()
                page.screenshot(path=str(OUT / "source-discovery-mobile-dark.png"), full_page=True)
                page.get_by_label("Color theme", exact=True).select_option("light")
        checked("Expanded source suggestions fit 390/768/1024px with dark and light themes")
        page.set_viewport_size({"width": 1440, "height": 1050})
        board_row = panel.locator(".operational-list > div").filter(has=page.get_by_text("SYNTHETIC small employer", exact=True))
        board_row.get_by_role("checkbox").check()
        expect(board_row.get_by_role("button", name="Enable source", exact=True)).to_be_enabled()
        board_row.get_by_role("button", name="Enable source", exact=True).click()
        panel.get_by_role("status").filter(has_text="Source enabled for read-only scans").wait_for()
        sources = context.request.get(base + "/api/sources").json()
        installed = next(row for row in sources if row["slug"] == "synthetic-small-browser")
        assert installed["permitted"] and installed["enabled"] and installed["last_success"] is None and installed["discovered_count"] == 0
        expect(panel.get_by_text("SYNTHETIC small employer", exact=True)).to_have_count(0)
        checked("Explicit review enables actual source without claiming a scan or opportunity")
        panel.get_by_role("button", name="Dismiss SYNTHETIC university program", exact=True).click()
        panel.get_by_role("status").filter(has_text="Source suggestion dismissed").wait_for()
        assert context.request.get(base + "/api/discovery/source-candidates").json()["total"] == 0
        page.reload()
        page.get_by_role("heading", name="Your opportunity notebook.").wait_for()
        page.get_by_role("button", name="Internship explorer", exact=True).click()
        page.get_by_text("Local places & discovery coverage", exact=True).click()
        page.get_by_text("New employer & program sources", exact=False).click()
        expect(page.get_by_text("No source suggestions awaiting review.", exact=False)).to_be_visible()
        with SessionLocal() as db:
            persisted = db.get(Source, parent.id)
            assert announcement["id"] in persisted.cache["dismissed_source_candidate_ids"]
        checked("Dismissal and installed-source filtering survive a browser reload")
        assert not errors, errors
        checked("No browser JavaScript errors")
        browser.close()
    report["passed"] = True
except Exception as exc:
    report["passed"] = False; report["failure"] = str(exc)[:2000]
    raise
finally:
    (OUT / "source-discovery-ui.json").write_text(json.dumps(report, indent=2) + "\n")
