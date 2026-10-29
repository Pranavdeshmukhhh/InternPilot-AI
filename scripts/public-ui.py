"""Local public-launch checks: synthetic demo, real app, no external actions."""

import json
import os
import shutil
import subprocess
from pathlib import Path
from datetime import datetime, UTC
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.getenv("UI_ARTIFACT_DIR", str(ROOT / "artifacts/phase9-public")))
OUT.mkdir(parents=True, exist_ok=True)
BASE = os.getenv("UI_TEST_URL", "http://127.0.0.1:3000")
report = {
    "at": datetime.now(UTC).isoformat(),
    "checks": [],
    "a11y": [],
    "measurements": {},
    "public_deployment": False,
}


def check(name):
    report["checks"].append(name)
    print(name + ": passed", flush=True)


try:
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=shutil.which("chromium"),
            headless=True,
            args=["--no-sandbox"],
        )
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        errors = []
        requests = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("request", lambda r: requests.append(r.url))
        page.add_init_script(
            "window.__v={lcp:0,cls:0};new PerformanceObserver(l=>{for(const e of l.getEntries())window.__v.lcp=e.startTime}).observe({type:'largest-contentful-paint',buffered:true});new PerformanceObserver(l=>{for(const e of l.getEntries())if(!e.hadRecentInput)window.__v.cls+=e.value}).observe({type:'layout-shift',buffered:true})"
        )
        page.goto(BASE)
        expect(page.get_by_role("heading", level=1)).to_contain_text("Less searching.")
        page.wait_for_timeout(1500)
        assert not [u for u in requests if "/api/" in u], requests
        report["measurements"]["initial_lab_observers"] = page.evaluate("window.__v")
        report["measurements"]["initial_js_decoded_bytes"] = page.evaluate(
            "performance.getEntriesByType('resource').filter(x=>new URL(x.name).pathname.endsWith('.js')).reduce((s,x)=>s+x.decodedBodySize,0)"
        )
        page.screenshot(path=str(OUT / "landing-desktop.png"), full_page=True)
        check("Public entry renders without signup or any backend API requests")
        axe = (ROOT / "frontend/node_modules/axe-core/axe.min.js").read_text()
        for width in [320, 360, 390, 768, 1440]:
            page.set_viewport_size({"width": width, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth"), (
                f"Overflow {width}"
            )
            if width == 390:
                page.screenshot(path=str(OUT / "landing-mobile.png"), full_page=True)
        check("Landing reflows at 320, 360, 390, 768 and 1440px")
        page.set_viewport_size({"width": 390, "height": 844})
        for theme in ["light", "dark"]:
            page.get_by_label("Color theme", exact=True).select_option(theme)
            for route in ["/", "/demo", "/privacy", "/terms", "/contact"]:
                page.goto(BASE + route)
                page.locator("main h1").wait_for()
                page.evaluate(axe)
                v = page.evaluate(
                    "async()=>{const r=await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa','wcag22aa']}});return r.violations.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.map(n=>n.target)}))}"
                )
                report["a11y"].append({"route": route, "theme": theme, "violations": v})
                assert not [x for x in v if x["impact"] in ["serious", "critical"]], v
                assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
        check(
            "Five public routes pass serious/critical axe gates in both themes on mobile"
        )
        page.get_by_label("Color theme", exact=True).select_option("light")
        page.goto(BASE + "/demo")
        page.get_by_label("Demo location", exact=True).select_option("International")
        expect(page.locator(".demo-row")).to_have_count(1)
        page.locator(".demo-row").first.click()
        dialog = page.get_by_role("dialog")
        expect(dialog).to_contain_text("EU work authorization")
        page.keyboard.press("Tab")
        assert dialog.evaluate("d=>d.contains(document.activeElement)")
        page.keyboard.press("Escape")
        expect(dialog).to_have_count(0)
        expect(page.locator(".demo-row").first).to_be_focused()
        page.get_by_label("Search demo opportunities").fill("nothing-matches")
        expect(
            page.get_by_role("heading", name="No examples match yet.")
        ).to_be_visible()
        page.get_by_role("button", name="Reset filters", exact=True).click()
        expect(page.locator(".demo-row")).to_have_count(5)
        page.get_by_label("Demo opportunity type", exact=True).select_option(
            "Hackathon"
        )
        expect(page.locator(".demo-row")).to_have_count(1)
        page.get_by_role("button", name="Application notebook", exact=True).click()
        expect(page.locator(".demo-pipeline section")).to_have_count(3)
        expect(page.locator(".demo-pipeline")).to_contain_text(
            "No application submitted"
        )
        page.reload()
        expect(page.get_by_role("heading", level=1)).to_contain_text(
            "Meet your opportunity notebook."
        )
        check(
            "Public demo search, region/type filters, empty recovery, detail focus and pipeline are functional"
        )
        assert not [u for u in requests if "/api/" in u]
        check(
            "All public/demo interactions are isolated from private APIs and persistence"
        )
        assert page.request.get(BASE + "/does-not-exist").status == 404
        assert page.request.get(BASE + "/robots.txt").status == 200
        assert page.request.get(BASE + "/icon.svg").status == 200
        response = page.request.get(BASE + "/social-image")
        assert response.status == 200 and response.headers["content-type"].startswith(
            "image/png"
        )
        (OUT / "social-preview.png").write_bytes(response.body())
        assert (
            "localhost" not in page.locator("head").inner_html()
            and "127.0.0.1" not in page.locator("head").inner_html()
        )
        check(
            "404, robots, vector icon and generated social PNG work without invented canonical URLs"
        )
        page.goto(BASE + "/login")
        expect(page.get_by_role("button", name="Sign in", exact=True)).to_be_visible()
        for theme in ["light", "dark"]:
            page.evaluate(
                "theme => document.documentElement.dataset.theme = theme", theme
            )
            assert page.locator(".brand-mark-shell svg").evaluate(
                "e => getComputedStyle(e.querySelector('rect')).fill !== getComputedStyle(e.querySelector('path')).stroke"
            ), f"Invisible brand mark in {theme} mode"
        check("Sign-in deep link opens sign-in rather than registration")
        # A mobile browser identity + network emulation is not a physical Instagram test.
        mobile = browser.new_context(
            viewport={"width": 390, "height": 844},
            is_mobile=True,
            has_touch=True,
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile Instagram",
        )
        m = mobile.new_page()
        cdp = mobile.new_cdp_session(m)
        cdp.send("Network.enable")
        cdp.send(
            "Network.emulateNetworkConditions",
            {
                "offline": False,
                "latency": 150,
                "downloadThroughput": 200000,
                "uploadThroughput": 100000,
                "connectionType": "cellular3g",
            },
        )
        m.goto(BASE)
        expect(
            m.get_by_role("link", name="Take a look inside", exact=True)
        ).to_be_visible()
        m.get_by_role("link", name="Take a look inside", exact=True).tap()
        m.wait_for_url("**/demo")
        expect(m.get_by_label("Search demo opportunities")).to_be_visible()
        m.get_by_label("Search demo opportunities").tap()
        m.get_by_label("Search demo opportunities").fill("Python")
        assert m.evaluate("document.documentElement.scrollWidth<=innerWidth")
        m.go_back()
        m.wait_for_url(BASE + "/")
        expect(m.get_by_role("heading", level=1)).to_contain_text("Less searching.")
        check(
            "Touch/in-app user-agent simulation with 150ms latency supports CTA, keyboard input and back navigation"
        )
        # Render the original vector mark as a local raster app icon.
        icon = context.new_page()
        icon.set_viewport_size({"width": 180, "height": 180})
        icon.goto(BASE + "/icon.svg")
        icon.locator("svg").evaluate(
            "e=>{e.style.width='180px';e.style.height='180px';document.body&&(document.body.style.margin='0')}"
        )
        icon.locator("svg").screenshot(
            path=str(ROOT / "frontend/public/apple-icon.png")
        )
        assert not errors, errors
        check("No JavaScript exceptions observed in the public-page journey")
        report["passed"] = True
        browser.close()
        lighthouse_cli = os.getenv("PUBLIC_LIGHTHOUSE_CLI")
        if lighthouse_cli:
            lighthouse = Path(lighthouse_cli)
            result = subprocess.run(
                [
                    shutil.which("node"),
                    str(lighthouse),
                    BASE,
                    "--chrome-flags=--no-sandbox --headless=new --disable-dev-shm-usage",
                    "--only-categories=performance,accessibility,best-practices,seo",
                    "--output=json",
                    "--output-path=" + str(OUT / "lighthouse-mobile.json"),
                    "--quiet",
                ],
                env={**os.environ, "CHROME_PATH": shutil.which("chromium")},
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            report["lighthouse_exit"] = result.returncode
            if result.returncode:
                report["lighthouse_error"] = result.stderr[-1200:]
            else:
                lh = json.loads((OUT / "lighthouse-mobile.json").read_text())
                report["lighthouse_scores"] = {
                    k: v["score"] for k, v in lh["categories"].items()
                }

finally:
    (OUT / "report.json").write_text(json.dumps(report, indent=2) + "\n")
