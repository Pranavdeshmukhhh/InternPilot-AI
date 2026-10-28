"""Studio UI acceptance. Only labeled fictional fixtures in a temporary DB."""
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
    raise SystemExit("Run through run-ui-acceptance.py --studio-ui with temporary data")
sys.path.insert(0, str(ROOT / "backend"))
from app.database import SessionLocal
from app.models import Opportunity, Source, SourceOpportunity
from app.security import digest
from app.services import canonical_fingerprint

OUT = ROOT / "artifacts"
report = {"at": datetime.now(UTC).isoformat(), "synthetic_data_only": True, "checks": [],
          "external_applications": 0, "external_emails": 0, "crawl_workers": 0}


def checked(name):
    report["checks"].append({"name": name, "passed": True})
    print(name + ": passed", flush=True)


def navigate(page, label):
    target = page.get_by_role("button", name=label, exact=True)
    if not target.is_visible() or not target.evaluate("el=>{const r=el.getBoundingClientRect();return r.right>0&&r.left<innerWidth;}"):
        page.get_by_role("button", name="Open navigation", exact=True).click()
    target.click()


try:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=shutil.which("chromium"), headless=True, args=["--no-sandbox"])
        context = browser.new_context(viewport={"width": 1440, "height": 1050}, color_scheme="dark")
        page = context.new_page(); page.set_default_timeout(20000)
        errors = []; page.on("pageerror", lambda error: errors.append(str(error)))
        base = os.getenv("UI_TEST_URL", "http://127.0.0.1:3000")
        page.goto(base)
        expect(page.locator("html")).to_have_attribute("data-theme", "light")
        expect(page.get_by_role("button", name="Create your workspace", exact=True)).to_be_visible()
        page.screenshot(path=str(OUT / "studio-auth.png"), full_page=False)
        checked("Light-first authentication uses the new interface without an OS-dark flash")
        page.get_by_label("Email address", exact=True).fill("studio-" + secrets.token_hex(5) + "@example.test")
        page.get_by_label("Password", exact=False).fill(secrets.token_urlsafe(24))
        page.get_by_role("button", name="Create your workspace", exact=True).click()
        page.get_by_role("heading", name="Your opportunity notebook.").wait_for()
        account = context.request.get(base + "/api/auth/session").json()
        fixtures = [
            ("Example Research", "Research Engineer Intern", "Pune, India", ["Python", "PyTorch"], True),
            ("Example Studio", "Software Engineering Intern", "Remote · India", ["TypeScript", "React"], True),
            ("Example Systems", "Cloud Engineering Intern", "Nagpur, India", ["AWS", "Python"], False),
            ("Example Computing", "Machine Learning Intern", "Bengaluru, India", ["Python", "SQL"], False),
            ("Example Labs", "Frontend Developer Intern", "Pune, India", ["React", "CSS"], True),
            ("Example University", "Undergraduate Research Intern", "Mumbai, India", ["Python"], False),
        ]
        with SessionLocal() as db:
            source = Source(owner_id=account["user"]["id"], kind="test", company="Fictional studio UI fixtures", permitted=False, enabled=False)
            db.add(source); db.flush()
            for index, (company, title, location, skills, remote) in enumerate(fixtures):
                data = {"title": title, "company": company, "location": location, "skills": skills, "remote": remote,
                        "url": f"https://fictional.example.invalid/internships/{index}", "opportunity_type": "internship",
                        "description": "Fictional local UI fixture. Eligibility requires review. Build software with the team and learn through practical projects.",
                        "deadline": "2099-06-30T18:30:00Z", "source": "local_test", "is_demo": True, "active": True,
                        "published_at": f"2026-10-{27-index:02d}T10:00:00Z"}
                row = Opportunity(fingerprint=digest(source.owner_id + canonical_fingerprint(data)), data=data)
                db.add(row); db.flush(); db.add(SourceOpportunity(source_id=source.id, opportunity_id=row.id))
            db.commit()
        page.reload(); page.get_by_role("heading", name="Your opportunity notebook.").wait_for()
        # Demo rows must not inflate real opportunity statistics.
        expect(page.locator(".metric-value").first).to_have_text("0")
        page.screenshot(path=str(OUT / "studio-overview.png"), full_page=False)
        navigate(page, "Internship explorer")
        expect(page.locator(".results-bar strong")).to_have_text("6")
        rows = page.locator(".studio-opportunity")
        expect(rows).to_have_count(6)
        assert rows.first.bounding_box()["height"] <= 180
        assert page.get_by_label("Search opportunities", exact=True).bounding_box()["y"] < 350
        assert page.get_by_text("Local places & discovery coverage", exact=True).bounding_box()["y"] > rows.first.bounding_box()["y"]
        page.screenshot(path=str(OUT / "studio-explorer-desktop.png"), full_page=False)
        checked("Compact opportunity rows keep title, location, deadline and eligibility ahead of setup controls")
        first = page.locator(".job-card").first
        title = first.locator("h3").inner_text()
        first.click()
        dialog = page.get_by_role("dialog")
        expect(dialog.get_by_role("heading", name=title, exact=True)).to_be_visible()
        box = dialog.bounding_box()
        assert box["x"] > 1440 / 2 and box["width"] <= 670 and box["height"] > 900
        expect(dialog.get_by_text("Verified requirements", exact=True)).to_be_visible()
        page.wait_for_timeout(300)  # Capture the completed sheet transition.
        page.screenshot(path=str(OUT / "studio-detail-desktop.png"), full_page=False)
        page.keyboard.press("Tab")
        assert dialog.evaluate("el=>el.contains(document.activeElement)")
        page.keyboard.press("Escape")
        expect(dialog).to_have_count(0)
        expect(first).to_be_focused()
        checked("Opportunity side sheet preserves evidence, keyboard trapping, Escape and return focus")
        save = page.get_by_role("button", name=f"Save {title}", exact=True)
        save.click()
        expect(page.get_by_role("button", name=f"Unsave {title}", exact=True)).to_have_attribute("aria-pressed", "true")
        navigate(page, "Saved opportunities")
        expect(page.locator(".results-bar strong")).to_have_text("1")
        expect(page.locator(".job-card h3")).to_have_text(title)
        checked("Independent bookmark actions save actual records and preserve the shortlist workflow")
        navigate(page, "Internship explorer")
        expect(page.locator(".results-bar strong")).to_have_text("6")
        dismiss = page.locator('.toast button')
        if dismiss.count():
            dismiss.click()
        for width in (390, 768, 1024):
            page.set_viewport_size({"width": width, "height": 900})
            expect(page.locator(".sidebar")).not_to_be_in_viewport()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), f"Page overflows at {width}px"
            page.evaluate("window.scrollTo(0,0)")
            if width == 390:
                for picker in (page.get_by_label('Color theme', exact=True), page.locator('.sort-control select')):
                    assert picker.evaluate("""el=>{const css=getComputedStyle(el);const canvas=document.createElement('canvas');const c=canvas.getContext('2d');c.font=css.font;return c.measureText(el.selectedOptions[0].label).width+parseFloat(css.paddingLeft)+parseFloat(css.paddingRight)+20<=el.clientWidth;}"""), "Native picker label is clipped"
                page.screenshot(path=str(OUT / "studio-explorer-mobile.png"), full_page=False)
                page.locator(".job-card").first.click()
                expect(page.get_by_role("dialog")).to_be_visible()
                assert page.get_by_role("dialog").bounding_box()["width"] <= width
                assert page.get_by_role("dialog").evaluate("el=>el.scrollWidth<=el.clientWidth")
                page.wait_for_timeout(300)
                page.screenshot(path=str(OUT / "studio-detail-mobile.png"), full_page=False)
                page.keyboard.press("Escape")
                expect(page.get_by_role("dialog")).to_have_count(0)
                page.get_by_label("Color theme", exact=True).select_option("dark")
                expect(page.locator("html")).to_have_attribute("data-theme", "dark")
                page.wait_for_timeout(200)
                page.screenshot(path=str(OUT / "studio-explorer-dark.png"), full_page=False)
                page.get_by_label("Color theme", exact=True).select_option("light")
        checked("Explorer and detail sheet fit mobile and tablet widths in light and dark themes")
        page.emulate_media(reduced_motion="reduce")
        duration = page.get_by_role("button", name="Filters", exact=True).evaluate("el=>getComputedStyle(el).transitionDuration")
        assert all(float(part.strip().removesuffix('s')) == 0 for part in duration.split(',')), duration
        assert not errors, errors
        checked("Reduced motion and all tested interactions complete without JavaScript errors")
        browser.close()
    report["passed"] = True
except Exception as exc:
    report["passed"] = False
    report["failure"] = str(exc)[:2000]
    raise
finally:
    (OUT / "studio-ui.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
