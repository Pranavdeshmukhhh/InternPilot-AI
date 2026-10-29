"""Synthetic owner-invitation and Terms rendering acceptance; no external sends."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ["UI_TEST_URL"]
OUT = ROOT / "artifacts/access-update/ui"
OUT.mkdir(parents=True, exist_ok=True)
PASSWORD = "synthetic-only-password-2049!"
report = {"checks": [], "external_actions": 0, "synthetic_only": True}


def check(message):
    report["checks"].append(message)
    print(message + ": passed", flush=True)


assert (
    os.environ.get("UI_TEST_ALLOW_OWNER_CLI") == "true"
    and os.environ.get("TEST_MODE") == "true"
)
subprocess.run(
    [
        sys.executable,
        "-c",
        "from unittest.mock import patch\nfrom app.admin import main\nwith patch('getpass.getpass',return_value='synthetic-only-password-2049!'):\n assert main(['create-owner','owner@example.invalid'])==0",
    ],
    cwd=ROOT / "backend",
    check=True,
    capture_output=True,
    text=True,
)
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
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(BASE + "/terms")
        expect(page.get_by_role("heading", level=1)).to_contain_text(
            "Before you begin."
        )
        page.wait_for_timeout(700)
        page.screenshot(path=str(OUT / "terms-desktop.png"), full_page=True)
        page.get_by_role("navigation", name="Terms sections").get_by_role(
            "link", name="Service limits"
        ).click()
        page.wait_for_timeout(700)
        assert page.locator("#limits").evaluate(
            "e=>e.getBoundingClientRect().top>=0 && e.getBoundingClientRect().top<innerHeight"
        )
        for width in [320, 390, 768]:
            page.set_viewport_size({"width": width, "height": 844})
            page.goto(BASE + "/terms")
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
            if width == 390:
                page.wait_for_timeout(700)
                page.screenshot(path=str(OUT / "terms-mobile.png"), full_page=True)
        reduced = browser.new_context(reduced_motion="reduce")
        r = reduced.new_page()
        r.goto(BASE + "/terms")
        assert (
            r.locator(".legal-intro").evaluate("e=>getComputedStyle(e).animationName")
            == "none"
        )
        assert (
            r.evaluate("getComputedStyle(document.documentElement).scrollBehavior")
            == "auto"
        )
        check("Terms anchor navigation, 320–1440px layouts and reduced-motion behavior")
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.goto(BASE + "/login")
        page.get_by_label("Email address", exact=True).fill("owner@example.invalid")
        page.get_by_label("Password", exact=True).fill(PASSWORD)
        page.get_by_role("button", name="Sign in", exact=True).click()
        expect(page.get_by_role("link", name="InternPilot overview")).to_be_visible()
        page.goto(BASE + "/owner")
        expect(
            page.get_by_role("heading", name="Workspace invitations", exact=True)
        ).to_be_visible()
        manager = page.locator(".invitation-manager")

        def issue(email):
            manager.get_by_label("Invited email address", exact=True).fill(email)
            manager.get_by_label("Confirm your owner password", exact=True).fill(
                PASSWORD
            )
            manager.get_by_label("I authorize this email address to join.").check()
            manager.get_by_role("button", name="Create invitation", exact=True).click()
            link = manager.get_by_label("One-time invitation link", exact=True)
            expect(link).to_be_visible()
            value = link.input_value()
            manager.get_by_role("button", name="Dismiss link", exact=True).click()
            return value

        link = issue("invited@example.invalid")
        check(
            "Owner creates a real email-bound invitation; one-time link can be dismissed"
        )
        guest = browser.new_context()
        member = guest.new_page()
        member.goto(link)
        expect(
            member.get_by_role("heading", name="Activate your invitation.", exact=True)
        ).to_be_visible()
        assert "#" not in member.url
        # A new invitation opened while already on /register must be read too.
        invitation_field = member.get_by_label("Invitation code", exact=True)
        invitation_field.fill("")
        fragment = urlsplit(link).fragment
        member.evaluate("fragment => { window.location.hash = fragment; }", fragment)
        expect(invitation_field).to_have_value(parse_qs(fragment)["invitation"][0])
        expect(member).to_have_url(BASE + "/register")
        member.get_by_label("Email address", exact=True).fill("wrong@example.invalid")
        member.get_by_label("Password", exact=True).fill(PASSWORD)
        with member.expect_response(
            lambda response: response.url.endswith("/api/auth/register")
        ) as result:
            member.get_by_role("button", name="Activate account", exact=True).click()
        assert result.value.status == 403
        member.get_by_label("Email address", exact=True).fill("invited@example.invalid")
        member.get_by_role("button", name="Activate account", exact=True).click()
        expect(member.get_by_role("link", name="InternPilot overview")).to_be_visible()
        assert guest.request.get(BASE + "/api/owner/invitations").status == 403
        check(
            "Invitation link is removed from history; wrong email rejected; approved account activates without owner privileges"
        )
        page.reload()
        expect(manager.locator(".invitation-list")).to_contain_text("used")
        revoked = issue("revoked@example.invalid")
        manager.locator(".invitation-list li").filter(
            has_text="revoked@example.invalid"
        ).get_by_role("button", name="Revoke invitation").click()
        manager.get_by_label("Confirm your owner password", exact=True).fill(PASSWORD)
        manager.get_by_label("I authorize revoking this invitation.").check()
        manager.get_by_role("button", name="Confirm revocation", exact=True).click()
        expect(manager.locator(".invitation-list")).to_contain_text("revoked")
        fresh = browser.new_context()
        f = fresh.new_page()
        f.goto(revoked)
        f.get_by_label("Email address", exact=True).fill("revoked@example.invalid")
        f.get_by_label("Password", exact=True).fill(PASSWORD)
        with f.expect_response(
            lambda response: response.url.endswith("/api/auth/register")
        ) as result:
            f.get_by_role("button", name="Activate account", exact=True).click()
        assert result.value.status == 403
        check(
            "Owner revocation prevents activation through the actual registration form"
        )
        axe = (ROOT / "frontend/node_modules/axe-core/axe.min.js").read_text()
        report["a11y"] = []
        for route in ["/terms", "/login"]:
            for theme in ["light", "dark"]:
                f.goto(BASE + route)
                f.get_by_label("Color theme", exact=True).select_option(theme)
                f.evaluate(axe)
                violations = f.evaluate(
                    "async()=>{const r=await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}});return r.violations.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))}))}"
                )
                report["a11y"].append(
                    {"route": route, "theme": theme, "violations": violations}
                )
                assert not [
                    v for v in violations if v["impact"] in ["serious", "critical"]
                ], violations
        manager.screenshot(path=str(OUT / "owner-invitations.png"))
        f.set_viewport_size({"width": 1440, "height": 1000})
        f.goto(BASE + "/login")
        expect(
            f.get_by_role("heading", name="Welcome back.", exact=True)
        ).to_be_visible()
        f.screenshot(path=str(OUT / "login-desktop.png"), full_page=True)
        assert not errors, errors
        check(
            "Terms/login accessibility gates pass in both themes; no observed JavaScript errors"
        )
        report["passed"] = True
        browser.close()
finally:
    (OUT / "report.json").write_text(json.dumps(report, indent=2) + "\n")
