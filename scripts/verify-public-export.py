"""Exercise the exact static export locally, optionally with mobile Lighthouse.

No backend, real user data, provider credentials, or external application actions.
Install matching frontend dependencies first. Lighthouse is an optional QA tool,
not a production dependency; pass its CLI explicitly with --lighthouse-cli.
"""

import argparse
import gzip
import json
import os
import shutil
import subprocess
from contextlib import contextmanager
from datetime import UTC, datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from playwright.sync_api import expect, sync_playwright


@contextmanager
def local_export(directory):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(directory), **kwargs)

        def log_message(self, *args):
            pass

        def translate_path(self, path):
            candidate = super().translate_path(path)
            if not Path(candidate).exists() and Path(candidate + ".html").is_file():
                return candidate + ".html"
            return candidate

        def do_GET(self):
            candidate = Path(self.translate_path(self.path))
            if candidate.is_dir():
                candidate = candidate / "index.html"
            if candidate.is_file() and "gzip" in self.headers.get(
                "Accept-Encoding", ""
            ):
                body = gzip.compress(candidate.read_bytes())
                self.send_response(200)
                self.send_header("Content-Type", self.guess_type(str(candidate)))
                self.send_header("Content-Encoding", "gzip")
                self.send_header("Vary", "Accept-Encoding")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    # A browser may cancel a prefetched resource during navigation.
                    pass
            else:
                super().do_GET()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--lighthouse-cli", type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    if not (directory / "index.html").is_file():
        parser.error("Build the public-only static export first")
    args.output.mkdir(parents=True, exist_ok=True)
    report = {
        "at": datetime.now(UTC).isoformat(),
        "environment": "local gzip-compressed static export; headless Chromium",
        "live_browser_test": False,
        "external_actions": 0,
        "checks": [],
    }
    try:
        with local_export(directory) as origin, sync_playwright() as pw:
            browser = pw.chromium.launch(
                executable_path=shutil.which("chromium"),
                headless=True,
                args=["--no-sandbox"],
            )
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            page = context.new_page()
            errors, api = [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on(
                "request",
                lambda request: (
                    api.append(request.url) if "/api/" in request.url else None
                ),
            )
            page.goto(origin)
            expect(page.get_by_role("heading", level=1)).to_contain_text(
                "Less searching."
            )
            expect(page.get_by_role("link", name="Open-source notices")).to_be_visible()
            notice = context.request.get(origin + "/third-party-notices.txt")
            assert (
                notice.status == 200
                and "react@" in notice.text()
                and "next@" in notice.text()
            )
            assert not page.locator('a[href="/register"]').count()
            page.screenshot(path=str(args.output / "desktop.png"), full_page=True)
            for width in [320, 390, 768]:
                page.set_viewport_size({"width": width, "height": 844})
                assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
                if width == 390:
                    page.screenshot(
                        path=str(args.output / "mobile.png"), full_page=True
                    )
            report["checks"].append(
                "Static landing, no unavailable account links, 320–1440px layouts"
            )
            page.get_by_role("link", name="Take a look inside", exact=True).click()
            page.wait_for_url("**/demo")
            expect(page.locator(".demo-row")).to_have_count(5)
            page.get_by_label("Demo location", exact=True).select_option(
                "International"
            )
            expect(page.locator(".demo-row")).to_have_count(1)
            page.locator(".demo-row").click()
            expect(page.get_by_role("dialog")).to_contain_text("EU work authorization")
            page.keyboard.press("Tab")
            assert page.get_by_role("dialog").evaluate(
                "d=>d.contains(document.activeElement)"
            )
            page.keyboard.press("Escape")
            expect(page.locator(".demo-row")).to_be_focused()
            page.reload()
            expect(page.locator(".demo-row")).to_have_count(5)
            page.screenshot(path=str(args.output / "demo-mobile.png"), full_page=True)
            report["checks"].append(
                "Static client navigation, filters, lazy drawer, focus, reload"
            )
            for route in ["/privacy", "/terms", "/contact"]:
                page.goto(origin + route)
                expect(page.locator("main h1")).to_be_visible()
            page.goto(origin + "/login")
            expect(page.locator("main h1")).to_contain_text("opportunity workspace.")
            assert (
                page.locator('input[type="password"],input[type="email"]').count() == 0
            )
            expect(
                page.get_by_text(
                    "Account sign-in is not available on this preview.", exact=True
                )
            ).to_be_visible()
            page.get_by_role(
                "link", name="Explore the public demo", exact=False
            ).click()
            page.wait_for_url("**/demo")
            report["checks"].append(
                "Public sign-in explains invitation-only access without collecting credentials; demo stays public"
            )
            for path in [
                "/register",
                "/overview",
                "/applications",
                "/api/health",
            ]:
                assert context.request.get(origin + path).status == 404, path
            assert not errors and not api, {"errors": errors, "api": api}
            report["checks"].append(
                "Policies render; private routes absent; no API traffic or JS exceptions"
            )
            report["passed"] = True
            browser.close()
            if args.lighthouse_cli:
                result = subprocess.run(
                    [
                        shutil.which("node"),
                        str(args.lighthouse_cli.resolve()),
                        origin,
                        "--chrome-flags=--no-sandbox --headless=new --disable-dev-shm-usage",
                        "--only-categories=performance,accessibility,best-practices,seo",
                        "--output=json",
                        "--output-path="
                        + str((args.output / "lighthouse-mobile.json").resolve()),
                        "--quiet",
                    ],
                    env={**os.environ, "CHROME_PATH": shutil.which("chromium")},
                    capture_output=True,
                    text=True,
                    timeout=150,
                    check=False,
                )
                report["lighthouse_exit"] = result.returncode
                if result.returncode:
                    report["lighthouse_error"] = result.stderr[-1200:]
                else:
                    lighthouse = json.loads(
                        (args.output / "lighthouse-mobile.json").read_text()
                    )
                    report["lighthouse_scores"] = {
                        k: v["score"] for k, v in lighthouse["categories"].items()
                    }
                    report["lighthouse_metrics"] = {
                        k: lighthouse["audits"][k]["numericValue"]
                        for k in [
                            "first-contentful-paint",
                            "largest-contentful-paint",
                            "total-blocking-time",
                            "cumulative-layout-shift",
                            "speed-index",
                        ]
                    }
        print(json.dumps(report, indent=2))
    finally:
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
