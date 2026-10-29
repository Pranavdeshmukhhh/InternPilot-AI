"""Private founder browser acceptance against isolated fixtures. Never real mail."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.parse import urlsplit, parse_qs

import httpx
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.founder_security import totp

BASE = os.environ["UI_TEST_URL"]
OUT = ROOT / "artifacts/founder/ui"
OUT.mkdir(parents=True, exist_ok=True)
PASSWORD = "synthetic-only-password-2049!"
assert (
    os.getenv("TEST_MODE") == "true" and os.getenv("UI_TEST_ALLOW_OWNER_CLI") == "true"
)
subprocess.run(
    [
        sys.executable,
        "-c",
        "from unittest.mock import patch\nfrom app.admin import main\nwith patch('getpass.getpass',return_value='synthetic-only-password-2049!'):\n assert main(['create-owner','founder@example.invalid'])==0",
    ],
    cwd=ROOT / "backend",
    capture_output=True,
    text=True,
    check=True,
)
with httpx.Client(base_url=BASE, trust_env=False) as client:
    assert (
        client.post(
            "/api/auth/register",
            json={"email": "member@example.invalid", "password": PASSWORD},
        ).status_code
        == 200
    )
report = {"checks": [], "external_actions": 0, "synthetic_only": True}


def check(message):
    report["checks"].append(message)
    print(message + ": passed", flush=True)


try:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=shutil.which("chromium"),
            headless=True,
            args=["--no-sandbox"],
        )
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(BASE + "/login")
        page.get_by_label("Email address", exact=True).fill("founder@example.invalid")
        page.get_by_label("Password", exact=True).fill(PASSWORD)
        page.get_by_role("button", name="Sign in", exact=True).click()
        expect(page.get_by_role("link", name="InternPilot overview")).to_be_visible()
        page.goto(BASE + "/owner")
        page.get_by_label("Founder password", exact=True).fill(PASSWORD)
        page.get_by_label("I authorize this audited administration session.").check()
        page.get_by_role("button", name="Unlock founder console", exact=True).click()
        expect(page.locator(".founder-facts").first).to_contain_text("members")
        page.screenshot(path=str(OUT / "overview-desktop.png"), full_page=True)
        for width in [320, 390, 768]:
            page.set_viewport_size({"width": width, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
            if width == 390:
                page.screenshot(path=str(OUT / "overview-mobile.png"), full_page=True)
        page.set_viewport_size({"width": 1440, "height": 1000})
        nav = page.get_by_role("navigation", name="Founder sections")
        for tab in [
            "Activity",
            "Analytics",
            "Security",
            "Applications",
            "Automation",
            "Infrastructure",
            "Settings",
        ]:
            with page.expect_response(
                lambda r: r.url.endswith("/api/owner/report?section=" + tab.lower())
            ) as result:
                nav.get_by_role("button", name=tab, exact=True).click()
            assert result.value.status == 200
        check("Founder unlock, seven live report projections and 320–1440px layout")
        nav.get_by_role("button", name="Members", exact=True).click()
        row = page.get_by_role("row").filter(has_text="member@example.invalid")
        row.get_by_role("button", name="Issue reset link").click()
        dialog = page.get_by_role("dialog")
        dialog.get_by_label("Access reason", exact=True).fill(
            "Synthetic account recovery requested"
        )
        dialog.get_by_label("Your owner password", exact=True).fill(PASSWORD)
        dialog.get_by_role("checkbox").check()
        dialog.get_by_role("button", name="Confirm owner action", exact=True).click()
        field = page.get_by_label("Password recovery link", exact=True)
        expect(field).to_be_visible()
        link = field.input_value()
        token = parse_qs(urlsplit(link).fragment)["recovery"][0]
        page.get_by_role("button", name="Dismiss recovery link", exact=True).click()
        guest = browser.new_context()
        g = guest.new_page()
        g.goto(link)
        expect(g.get_by_label("Recovery code", exact=True)).to_have_value(token)
        g.get_by_label("New password", exact=True).fill(
            "synthetic-recovered-password-42!"
        )
        g.get_by_label("Confirm new password", exact=True).fill(
            "synthetic-recovered-password-42!"
        )
        g.get_by_role("button", name="Set new password", exact=True).click()
        expect(
            g.get_by_role("heading", name="A fresh start.", exact=True)
        ).to_be_visible()
        check(
            "Founder issues a one-time recovery link and recipient chooses a new password through the real UI"
        )
        nav.get_by_role("button", name="Security", exact=True).click()
        page.get_by_label("Confirm current password for MFA", exact=True).fill(PASSWORD)
        page.get_by_role("button", name="Set up MFA", exact=True).click()
        seed = page.get_by_label("Authenticator setup key", exact=True)
        expect(seed).to_be_visible()
        secret = seed.input_value()
        page.get_by_label("Confirm current password for MFA", exact=True).fill(PASSWORD)
        page.get_by_label("Fresh authenticator code", exact=True).fill(
            totp(secret, int(time.time()) // 30)
        )
        page.get_by_role("button", name="Confirm and enable MFA", exact=True).click()
        expect(
            page.get_by_role("button", name="Disable MFA", exact=True)
        ).to_be_visible()
        fresh = browser.new_context()
        f = fresh.new_page()
        f.goto(BASE + "/login")
        f.get_by_label("Email address", exact=True).fill("founder@example.invalid")
        f.get_by_label("Password", exact=True).fill(PASSWORD)
        with f.expect_response(lambda r: r.url.endswith("/api/auth/login")) as result:
            f.get_by_role("button", name="Sign in", exact=True).click()
        assert result.value.status == 403
        # A new time step within the supported +30s authenticator window avoids reuse.
        f.get_by_label("Authenticator code", exact=True).fill(
            totp(secret, int(time.time()) // 30 + 1)
        )
        f.get_by_role("button", name="Sign in", exact=True).click()
        expect(f.get_by_role("link", name="InternPilot overview")).to_be_visible()
        check(
            "Authenticator setup/confirmation and MFA-required sign-in work without seed readback"
        )
        nav.get_by_role("button", name="Overview", exact=True).click()
        # Enabling MFA changes security_version, invalidating the earlier unlock grant.
        expect(
            page.get_by_role("button", name="Unlock founder console", exact=True)
        ).to_be_visible()
        page.get_by_label("Founder password", exact=True).fill(PASSWORD)
        page.get_by_label("I authorize this audited administration session.").check()
        page.get_by_role("button", name="Unlock founder console", exact=True).click()
        expect(page.locator(".founder-facts").first).to_contain_text("members")
        axe = (ROOT / "frontend/node_modules/axe-core/axe.min.js").read_text()
        page.evaluate(axe)
        violations = page.evaluate(
            "async()=>{const r=await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}});return r.violations.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.map(n=>n.target)}))}"
        )
        report["a11y"] = violations
        assert not [v for v in violations if v["impact"] in ["serious", "critical"]], (
            violations
        )
        assert not errors, errors
        check(
            "MFA change invalidates report grant; fresh unlock and automated accessibility gates pass"
        )
        report["passed"] = True
        browser.close()
finally:
    (OUT / "report.json").write_text(json.dumps(report, indent=2) + "\n")
