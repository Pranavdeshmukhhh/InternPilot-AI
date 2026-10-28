"""Actual browsing/theme checks using isolated, labeled synthetic records only."""
import json
import os
import secrets
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
if os.getenv("UI_TEST_ALLOW_OWNER_CLI") != "true" or "internpilot-ui-" not in os.getenv("DATABASE_URL", ""):
    raise SystemExit("Use run-ui-acceptance.py --warm-ui; a fresh temporary database is required")
sys.path.insert(0, str(ROOT / "backend"))
from app.database import SessionLocal
from app.models import Opportunity, Source, SourceOpportunity
from app.security import digest
from app.services import canonical_fingerprint

OUT = ROOT / "artifacts"
report = {"at": datetime.now(UTC).isoformat(), "synthetic_data_only": True, "checks": [],
          "external_submissions": 0, "external_emails": 0, "live_searches": 0, "crawl_workers": 0}


def checked(name):
    report["checks"].append({"name": name, "passed": True})
    print(name + ": passed", flush=True)


def navigate(page, name):
    expect(page.locator(".detail-sheet[data-state='closed']")).to_have_count(0)
    button = page.get_by_role("button", name=name, exact=True)
    if not button.is_visible() or not button.evaluate("el=>{const r=el.getBoundingClientRect();return r.right>0&&r.left<innerWidth;}"):
        page.get_by_role("button", name="Open navigation", exact=True).click()
    button.click()


def contrast(page, selector):
    return page.locator(selector).first.evaluate("""element => {
      const css=getComputedStyle(element);
      const rgb=value => (value.match(/[\\d.]+/g)||[]).slice(0,3).map(Number);
      const luminance=value => rgb(value).map(c=>c/255).map(c=>c<=.04045?c/12.92:((c+.055)/1.055)**2.4).reduce((sum,c,i)=>sum+c*[.2126,.7152,.0722][i],0);
      const a=luminance(css.color), b=luminance(css.backgroundColor);
      return {ratio:(Math.max(a,b)+.05)/(Math.min(a,b)+.05), text:css.color, background:css.backgroundColor};
    }""")


try:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=shutil.which("chromium"), headless=True, args=["--no-sandbox"])
        context = browser.new_context(viewport={"width": 1440, "height": 1050}, color_scheme="dark")
        # Keep the real EventSource connection; capture it only to exercise
        # normal UI invalidation signals without a provider or crawl worker.
        context.add_init_script("""(() => {
          const Native=window.EventSource;
          window.__internpilotTestStreams=[];
          window.EventSource=class extends Native {
            constructor(...args) { super(...args); window.__internpilotTestStreams.push(this); }
          };
        })();""")
        page = context.new_page(); page.set_default_timeout(20000)
        errors = []; page.on("pageerror", lambda error: errors.append(str(error)))
        base = os.getenv("UI_TEST_URL", "http://127.0.0.1:3000")
        page.goto(base)
        assert context.request.get(base + "/api/health").json()["test_mode"]
        expect(page.locator("html")).to_have_attribute("data-theme", "light")
        checked("First visit uses light mode even when the operating system prefers dark")
        page.get_by_label("Email address", exact=True).fill("warm-ui-" + secrets.token_hex(5) + "@example.test")
        page.get_by_label("Password", exact=False).fill(secrets.token_urlsafe(24))
        page.get_by_role("button", name="Create your workspace", exact=True).click()
        page.get_by_role("heading", name="Your opportunity notebook.").wait_for()
        theme = page.get_by_label("Color theme", exact=True)
        expect(theme).to_have_value("light")
        theme.select_option("dark")
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        page.reload()
        page.get_by_role("heading", name="Your opportunity notebook.").wait_for()
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        expect(page.get_by_label("Color theme", exact=True)).to_have_value("dark")
        page.get_by_label("Color theme", exact=True).select_option("system")
        expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        page.emulate_media(color_scheme="light")
        expect(page.locator("html")).to_have_attribute("data-theme", "light")
        page.get_by_label("Color theme", exact=True).select_option("light")
        checked("Explicit dark and system preferences persist and respond to system changes")
        session = context.request.get(base + "/api/auth/session").json()
        with SessionLocal() as db:
            source = Source(owner_id=session["user"]["id"], kind="test", slug="warm-ui-synthetic", company="SYNTHETIC browser fixture", enabled=False, permitted=False)
            db.add(source); db.flush()
            for index in range(26):
                role = "Python" if index % 2 == 0 else "Cloud"
                data = {"title": f"SYNTHETIC {role} Intern {index:02}", "company": "SYNTHETIC Paper Lab",
                        "url": f"https://synthetic.example.invalid/internship/{index}", "location": "Pune" if index < 15 else "Nagpur",
                        "remote": False, "opportunity_type": "internship", "source": "local_test", "is_demo": True,
                        "description": "Synthetic local browser fixture. Verify eligibility.", "skills": [role], "active": True,
                        "published_at": f"2026-10-{index + 1:02}T00:00:00+00:00"}
                job = Opportunity(fingerprint=digest(source.owner_id + canonical_fingerprint(data)), data=data)
                db.add(job); db.flush(); db.add(SourceOpportunity(source_id=source.id, opportunity_id=job.id))
            db.commit()
        navigate(page, "Internship explorer")
        expect(page.locator(".results-bar strong")).to_have_text("26")
        expect(page.locator(".job-card")).to_have_count(20)
        page.wait_for_timeout(250)
        body_colors = contrast(page, "body")
        action_colors = contrast(page, ".page-title-row .btn-primary")
        assert body_colors["ratio"] >= 4.5, body_colors
        assert action_colors["ratio"] >= 4.5, action_colors
        panel_radius = page.locator(".opportunity-list").locator("..").evaluate("el=>parseFloat(getComputedStyle(el).borderTopLeftRadius)")
        assert 16 <= panel_radius <= 32, panel_radius
        report["contrast"] = {"body": body_colors, "primary_action": action_colors}
        page.get_by_label("Search opportunities", exact=True).focus()
        # Keyboard users need a visible indicator, whether outline or focus ring.
        page.keyboard.press("Tab"); page.keyboard.press("Shift+Tab")
        focus = page.evaluate("""() => { const element=document.activeElement; const css=getComputedStyle(element.closest('.search-input')||element); return {outline:css.outlineStyle,width:parseFloat(css.outlineWidth),shadow:css.boxShadow}; }""")
        assert focus["outline"] != "none" and focus["width"] > 0 or focus["shadow"] != "none", focus
        checked("Warm surfaces retain readable text/action contrast, curved panels and keyboard focus")
        search = page.get_by_label("Search opportunities", exact=True)
        search.fill("Python")
        expect(page.locator(".results-bar strong")).to_have_text("13")
        sort = page.locator(".sort-control select")
        sort.select_option("newest")
        expect(page.locator(".job-card h3").first).to_have_text("SYNTHETIC Python Intern 24")
        page.locator(".job-card").first.click()
        expect(page.get_by_role("dialog")).to_be_visible()
        page.get_by_role("button", name="Close dialog", exact=True).click()
        expect(search).to_have_value("Python")
        navigate(page, "Overview")
        navigate(page, "Internship explorer")
        expect(page.get_by_label("Search opportunities", exact=True)).to_have_value("Python")
        expect(page.locator(".sort-control select")).to_have_value("newest")
        expect(page.locator(".results-bar strong")).to_have_text("13")
        page.reload()
        page.get_by_role("heading", name="Your opportunity notebook.").wait_for()
        navigate(page, "Internship explorer")
        expect(page.get_by_label("Search opportunities", exact=True)).to_have_value("Python")
        expect(page.locator(".results-bar strong")).to_have_text("13")
        checked("Search and sorting survive details, navigation and reload within the private browser session")
        requests = []
        page.on("request", lambda request: requests.append(request.url) if "/api/opportunities/page?" in request.url else None)
        search = page.get_by_label("Search opportunities", exact=True)
        search.fill("")
        expect(page.locator(".results-bar strong")).to_have_text("26")
        search.press_sequentially("Cloud", delay=30)
        expect(page.locator(".results-bar strong")).to_have_text("13")
        searched = [parse_qs(urlsplit(url).query).get("search", [""])[0] for url in requests]
        assert "Cloud" in searched and not any(value in {"C", "Cl", "Clo", "Clou"} for value in searched), searched
        checked("Typing is debounced so partial search terms do not issue redundant requests")
        search.fill("")
        expect(page.locator(".results-bar strong")).to_have_text("26")
        held = []
        def hold_python(route):
            query = parse_qs(urlsplit(route.request.url).query).get("search", [""])[0]
            if query == "Python":
                held.append(route)
            else:
                route.continue_()
        page.route("**/api/opportunities/page?**", hold_python)
        search.fill("Python")
        until = time.monotonic() + 10
        while not held and time.monotonic() < until:
            page.wait_for_timeout(25)
        assert held, "Expected the deliberately delayed query"
        expect(page.locator(".job-card")).to_have_count(0)
        expect(page.get_by_role("region", name="Opportunity results", exact=True).get_by_role("status")).to_have_text("Updating results…")
        search.fill("Cloud")
        expect(page.locator(".results-bar strong")).to_have_text("13")
        expect(page.locator(".job-card h3").first).to_contain_text("Cloud")
        for route in held:
            if route.request.failure:
                assert "ERR_ABORTED" in route.request.failure or "cancel" in route.request.failure.lower(), route.request.failure
                try:
                    route.abort()
                except PlaywrightError:
                    pass  # A browser-canceled interception may already be gone.
                continue
            response = context.request.get(route.request.url)
            try:
                route.fulfill(response=response)
            except PlaywrightError:
                # AbortController may cancel the old network request while its
                # delayed server response is being released. Cancellation itself
                # is a valid defense against stale results.
                assert route.request.failure and ("ERR_ABORTED" in route.request.failure or "cancel" in route.request.failure.lower()), route.request.failure
        page.wait_for_timeout(250)
        assert all("Cloud" in title for title in page.locator(".job-card h3").all_text_contents())
        page.unroute("**/api/opportunities/page?**", hold_python)
        checked("Changed-query loading hides old rows and late responses cannot replace current matches")
        def outage(route):
            query = parse_qs(urlsplit(route.request.url).query).get("search", [""])[0]
            if query == "SYNTHETIC outage":
                route.fulfill(status=503, content_type="application/json", body=json.dumps({"detail": "Synthetic opportunity query unavailable"}))
            else:
                route.continue_()
        page.route("**/api/opportunities/page?**", outage)
        search.fill("SYNTHETIC outage")
        failure = page.get_by_role("alert").filter(has_text="Synthetic opportunity query unavailable")
        expect(failure).to_be_visible()
        expect(page.get_by_role("region", name="Opportunity results", exact=True)).to_have_attribute("aria-busy", "false")
        expect(page.locator(".results-bar")).not_to_contain_text("Loading")
        expect(page.locator(".results-bar")).not_to_contain_text("Updating")
        page.unroute("**/api/opportunities/page?**", outage)
        failure.get_by_role("button", name="Try again", exact=True).click()
        expect(page.locator(".results-bar strong")).to_have_text("0")
        expect(failure).to_have_count(0)
        search.fill("Cloud")
        expect(page.locator(".results-bar strong")).to_have_text("13")
        checked("A failed query stops loading, explains the error and recovers through Try again")
        # Reset is a user-visible action; it clears remembered search and filters.
        page.get_by_role("button", name="Filters", exact=True).click()
        page.get_by_role("button", name="Reset filters", exact=True).click()
        expect(page.locator(".results-bar strong")).to_have_text("26")
        expect(search).to_have_value("")
        expect(page.locator(".job-card")).to_have_count(20)
        page.get_by_role("button", name="Next", exact=True).click()
        expect(page.locator(".job-card")).to_have_count(6)
        expect(page.locator(".results-heading")).to_be_focused()
        expect(page.locator(".pagination")).to_contain_text("Page 2 of 2")
        page.get_by_role("button", name="Previous", exact=True).click()
        expect(page.locator(".job-card")).to_have_count(20)
        checked("Reset clears filters and pagination loads the correct result slice")
        # Keep the screenshot useful rather than presenting 26 synthetic rows.
        search.fill("Cloud")
        expect(page.locator(".results-bar strong")).to_have_text("13")
        page.get_by_role("button", name="Filters", exact=True).click()
        page.evaluate("window.scrollTo(0,0)")
        page.screenshot(path=str(OUT / "warm-explorer-desktop.png"), full_page=False)
        for width in (390, 768, 1024):
            page.set_viewport_size({"width": width, "height": 900})
            expect(page.locator(".sidebar")).not_to_be_in_viewport()
            assert page.evaluate("document.documentElement.scrollWidth<=window.innerWidth"), f"Explorer overflows at {width}px"
            if width == 390:
                page.screenshot(path=str(OUT / "warm-explorer-mobile.png"), full_page=False)
                page.get_by_label("Color theme", exact=True).select_option("dark")
                expect(page.locator("html")).to_have_attribute("data-theme", "dark")
                page.wait_for_timeout(250)
                dark_body = contrast(page, "body")
                dark_action = contrast(page, ".page-title-row .btn-primary")
                assert dark_body["ratio"] >= 4.5 and dark_action["ratio"] >= 4.5, (dark_body, dark_action)
                report["contrast"]["dark_body"] = dark_body
                report["contrast"]["dark_primary_action"] = dark_action
                page.screenshot(path=str(OUT / "warm-explorer-mobile-dark.png"), full_page=False)
                page.get_by_label("Color theme", exact=True).select_option("light")
        checked("Light and dark explorers fit 390/768/1024px and maintain readable contrast")
        page.emulate_media(reduced_motion="reduce")
        motion = page.get_by_role("button", name="Find opportunities", exact=True).evaluate("el=>getComputedStyle(el).transitionDuration")
        assert all(float(value.strip().removesuffix("s")) <= .01 for value in motion.split(",")), motion
        checked("Reduced-motion preference suppresses animated control transitions")
        page.get_by_role("heading", name="Internships", exact=True).click()
        page.keyboard.press("/")
        expect(page.get_by_label("Search opportunities", exact=True)).to_be_focused()
        expect(page.get_by_label("Search opportunities", exact=True)).to_have_value("Cloud")
        checked("The search keyboard shortcut focuses the field without entering a stray slash")
        page.wait_for_function("window.__internpilotTestStreams.some(source=>source.readyState===EventSource.OPEN)")
        dashboard_requests = []
        page.on("request", lambda request: dashboard_requests.append(request.url) if urlsplit(request.url).path == "/api/dashboard" else None)
        page.evaluate("""() => {
          const source=window.__internpilotTestStreams.filter(value=>value.readyState===EventSource.OPEN).at(-1);
          for(let index=0;index<20;index++) source.dispatchEvent(new MessageEvent('message',{data:'synthetic invalidation signal'}));
        }""")
        until = time.monotonic() + 5
        while not dashboard_requests and time.monotonic() < until:
            page.wait_for_timeout(25)
        assert dashboard_requests, "Event signals should request a real dashboard refresh"
        page.wait_for_timeout(2200)
        assert len(dashboard_requests) <= 2, len(dashboard_requests)
        checked("Twenty real UI event signals coalesce into at most two dashboard refreshes")
        # Simulate the browser lifecycle property rather than changing any API
        # data. The actual polling interval and visibility handler still run.
        page.evaluate("""() => {
          window.__internpilotTestHidden=true;
          Object.defineProperty(document,'hidden',{configurable:true,get:()=>window.__internpilotTestHidden});
          document.dispatchEvent(new Event('visibilitychange'));
        }""")
        dashboard_requests.clear()
        page.wait_for_timeout(16000)
        assert not dashboard_requests, len(dashboard_requests)
        page.evaluate("window.__internpilotTestHidden=false;document.dispatchEvent(new Event('visibilitychange'))")
        until = time.monotonic() + 5
        while not dashboard_requests and time.monotonic() < until:
            page.wait_for_timeout(25)
        assert dashboard_requests, "Returning to the visible tab should refresh current data"
        checked("Simulated hidden-tab lifecycle pauses actual polling and refreshes on return")
        page.get_by_role("button", name="Sign out", exact=True).click()
        page.get_by_label("Email address", exact=True).fill("warm-second-" + secrets.token_hex(5) + "@example.test")
        page.get_by_label("Password", exact=False).fill(secrets.token_urlsafe(24))
        page.get_by_role("button", name="Create your workspace", exact=True).click()
        page.get_by_role("heading", name="Your opportunity notebook.").wait_for()
        navigate(page, "Internship explorer")
        expect(page.get_by_label("Search opportunities", exact=True)).to_have_value("")
        expect(page.locator(".results-bar strong")).to_have_text("0")
        checked("A different account cannot inherit the previous user's filters or opportunity rows")
        assert not errors, errors
        checked("No browser JavaScript errors")
        browser.close()
    report["passed"] = True
except Exception as exc:
    report["passed"] = False
    report["failure"] = str(exc)[:2000]
    raise
finally:
    (OUT / "warm-ui.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
