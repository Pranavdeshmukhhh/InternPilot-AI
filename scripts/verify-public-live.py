"""Browser smoke for the explicitly selected public read-only preview only."""

import argparse
import json
import os
import shutil
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--origin", required=True)
p.add_argument("--output", type=Path, required=True)
args = p.parse_args()
u = urlsplit(args.origin)
if (
    u.scheme != "https"
    or not u.hostname
    or u.username
    or u.password
    or u.query
    or u.fragment
    or u.path not in {"", "/"}
):
    p.error("Exact HTTPS origin required")
args.output.mkdir(parents=True, exist_ok=True)
proxy = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")
launch = {
    "executable_path": shutil.which("chromium"),
    "headless": True,
    "args": ["--no-sandbox"],
}
if proxy:
    s = urlsplit(proxy)
    launch["proxy"] = {"server": f"{s.scheme}://{s.hostname}:{s.port or 8080}"}
    if s.username:
        launch["proxy"].update(username=s.username, password=s.password or "")
report = {"url": args.origin, "checks": [], "external_actions": 0}
try:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(**launch)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        page.set_default_timeout(20000)
        errors = []
        api = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("request", lambda r: api.append(r.url) if "/api/" in r.url else None)
        page.goto(args.origin)
        expect(page.get_by_role("heading", level=1)).to_contain_text("Less searching.")
        page.screenshot(path=str(args.output / "desktop.png"), full_page=True)
        for width in [320, 390, 768]:
            page.set_viewport_size({"width": width, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
            if width == 390:
                page.screenshot(path=str(args.output / "mobile.png"), full_page=True)
        report["checks"].append("Live landing and responsive screenshots")
        page.get_by_role("link", name="Take a look inside", exact=True).click()
        page.wait_for_url("**/demo")
        expect(page.locator(".demo-row")).to_have_count(5)
        page.get_by_label("Demo location", exact=True).select_option("International")
        expect(page.locator(".demo-row")).to_have_count(1)
        page.locator(".demo-row").click()
        expect(page.get_by_role("dialog")).to_contain_text("EU work authorization")
        page.keyboard.press("Escape")
        expect(page.locator(".demo-row")).to_be_focused()
        page.reload()
        expect(page.locator(".demo-row")).to_have_count(5)
        page.screenshot(path=str(args.output / "demo-mobile.png"), full_page=True)
        assert not page.locator('a[href="/login"],a[href="/register"]').count()
        for path in ["/privacy", "/terms", "/contact"]:
            page.goto(args.origin + path)
            expect(page.locator("main h1")).to_be_visible()
        assert not api and not errors, {"api": api, "errors": errors}
        report["checks"].append(
            "Live client navigation, filters, drawer focus, reload, policies and API isolation"
        )
        report["passed"] = True
        browser.close()
finally:
    (args.output / "browser.json").write_text(json.dumps(report, indent=2) + "\n")
