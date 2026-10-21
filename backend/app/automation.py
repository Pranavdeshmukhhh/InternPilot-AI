"""Conservative Playwright application adapter.

Only the isolated InternPilot test portal supports a final automated click.
External static HTML forms support verified field preparation with page scripts
disabled and always require a human to finish them in the employer's browser. Adding an employer adapter requires a
separate authorization review and explicit implementation, not a URL allowlist.
"""
from __future__ import annotations

import asyncio
import inspect
import ipaddress
import os
import re
import shutil
import socket
from collections.abc import Callable
from typing import Any
from urllib.parse import urljoin, urlparse

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright

MAX_DOCUMENT_BYTES = 8 * 1024 * 1024
MAX_FIELDS = 100
# Exact labels only: speculative semantic mapping must not become verified data.
FIELD_MAP = {
    "full name": "name", "name": "name", "first name": "first_name", "last name": "last_name",
    "email": "email", "email address": "email", "phone": "phone", "phone number": "phone",
    "country": "country", "expected graduation year": "graduation_year", "graduation year": "graduation_year",
    "university": "university", "college": "university", "degree": "degree",
    "github": "github", "github url": "github", "linkedin": "linkedin", "linkedin url": "linkedin",
    "portfolio": "portfolio", "portfolio url": "portfolio",
}
SENSITIVE = re.compile(
    r"sponsor|visa|authori[sz]|right to work|criminal|disab|veteran|gender|race|ethnic|religion|"
    r"citizen|nationality|salary|compensation|consent|agree|terms|privacy|signature|certif|"
    r"date of birth|birth date|age|legal|government|passport|aadhaar|ssn|social security", re.I
)
CAPTCHA = ".g-recaptcha, .h-captcha, iframe[src*='recaptcha'], iframe[src*='hcaptcha'], [data-sitekey], input[autocomplete='one-time-code'], input[name*='otp' i], input[type='password']"


def _origin(value: str) -> str:
    p = urlparse(value)
    if p.scheme not in {"http", "https"} or not p.hostname or p.username or p.password or p.fragment:
        raise ValueError("Only explicit HTTP(S) application origins without credentials are supported")
    try:
        port = p.port
    except ValueError as exc:
        raise ValueError("Invalid application port") from exc
    host = p.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    if port is not None and not ((p.scheme == "https" and port == 443) or (p.scheme == "http" and port == 80)):
        host += f":{port}"
    return f"{p.scheme}://{host}"


def test_portal_origin() -> str:
    """The one explicit local test target; a generic localhost exemption is unsafe."""
    raw = os.getenv("TEST_PORTAL_ORIGIN", "http://127.0.0.1:8000")
    origin = _origin(raw)
    parsed = urlparse(raw)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1", "backend"}:
        raise ValueError("TEST_PORTAL_ORIGIN must name loopback or the isolated backend Compose service")
    if parsed.path not in {"", "/"} or parsed.query or origin != raw.rstrip("/"):
        raise ValueError("TEST_PORTAL_ORIGIN must be a canonical origin")
    return origin


async def _public_target(url: str, allowed: set[str], *, test_origin: str | None) -> None:
    origin = _origin(url)
    if origin not in allowed:
        raise ValueError("Application navigation left the approved origins")
    p = urlparse(url)
    if test_origin and origin == test_origin:
        if not p.path.startswith("/test-portal/"):
            raise ValueError("Only the isolated test-portal path is permitted locally")
        return
    if p.scheme != "https":
        raise ValueError("External application pages require HTTPS")
    host = p.hostname or ""
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        loop = asyncio.get_running_loop()
        try:
            records = await loop.getaddrinfo(host, p.port or 443, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise ValueError("The application hostname could not be resolved") from exc
        addresses = [ipaddress.ip_address(r[4][0]) for r in records]
    if not addresses or any(not a.is_global for a in addresses):
        raise ValueError("Private, loopback, and metadata application targets are forbidden")


def _result(status: str, reason: str, **kwargs: Any) -> dict:
    return {
        "status": status, "reason": reason, "screenshot": None,
        "confirmation_id": None, "confirmation_text": None, "session_state": None,
        "fields": [], **kwargs,
    }


async def _field_inventory(page: Any) -> list[dict]:
    return await page.locator("input, select, textarea").evaluate_all("""els => els
      .filter(el => el.type !== 'hidden' && !['submit','button','reset'].includes(el.type) && el.getClientRects().length)
      .map(el => ({tag:el.tagName.toLowerCase(),type:el.type || '',name:el.name || '',
        id:el.id || '',label:((el.labels && Array.from(el.labels).map(l=>l.textContent).join(' ')) ||
        el.getAttribute('aria-label') || '').replace(/\\s+/g,' ').trim(),
        required:el.required,disabled:el.disabled,readOnly:el.readOnly}))""")


async def run_application(
    *, url: str, profile: dict, resume: bytes, submit: bool, approved: bool,
    allowed_origins: list[str], test_mode: bool = False,
    before_submit: Callable | None = None, session_state: dict | None = None,
    before_upload: Callable | None = None,
) -> dict:
    """Fill verified answers, capture evidence, and submit only the test adapter.

    The caller must persist a SUBMITTING state inside before_submit before the
    final click; a crash from that state is an uncertain outcome, never a retry.
    Browser state is returned in memory for encryption by the caller.
    """
    if submit and not approved:
        return _result("needs_input", "Explicit submission approval is required")
    if not resume.startswith(b"%PDF-") or len(resume) > MAX_DOCUMENT_BYTES:
        return _result("needs_input", "A valid PDF resume of at most 8 MiB is required")
    try:
        allowed = {_origin(o) for o in allowed_origins}
        local_origin = test_portal_origin() if test_mode else None
        await _public_target(url, allowed, test_origin=local_origin)
    except ValueError as exc:
        return _result("needs_input", str(exc))
    is_test = bool(local_origin and _origin(url) == local_origin and urlparse(url).path == "/test-portal/apply")
    if submit and not is_test:
        return _result("needs_input", "This employer has no certified submission adapter; finish the application manually")
    if not is_test and before_upload is None:
        return _result("needs_input", "Specific approval for this resume upload is required before browser preparation")
    verified = set(profile.get("verified_fields") or [])
    fields: list[dict] = []
    screenshot = None
    attempted = False
    browser = None
    context = None
    try:
        async with async_playwright() as playwright:
            executable = os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE") or shutil.which("chromium")
            launch_options: dict[str, Any] = {"headless": True, "chromium_sandbox": not is_test}
            if executable:
                launch_options["executable_path"] = executable
            # Playwright defaults to an unsandboxed browser. Explicitly require
            # Chromium sandboxing for every external page. Only the isolated,
            # certified local fixture may run without it in restricted CI/Docker.
            # A missing external sandbox pauses preparation; no unsafe fallback.
            if is_test:
                launch_options["args"] = ["--no-sandbox"]
            browser = await playwright.chromium.launch(**launch_options)
            context = await browser.new_context(
                storage_state=session_state, accept_downloads=False, viewport={"width": 1200, "height": 1000},
                service_workers="block", permissions=[], java_script_enabled=is_test,
            )
            blocked_request = False

            async def guard(route: Any) -> None:
                nonlocal blocked_request
                request = route.request
                try:
                    await _public_target(request.url, allowed, test_origin=local_origin)
                    # Preparation cannot make background external mutations.
                    if request.method not in {"GET", "HEAD", "OPTIONS"} and not (is_test and attempted):
                        raise ValueError("Non-read application request blocked before approved submission")
                    if request.method not in {"GET", "HEAD", "OPTIONS"}:
                        expected = urljoin(url, "/test-portal/submit")
                        if request.url != expected:
                            raise ValueError("Unexpected submission endpoint")
                    await route.continue_()
                except (ValueError, PlaywrightError):
                    blocked_request = True
                    await route.abort("blockedbyclient")

            await context.route("**/*", guard)
            if hasattr(context, "route_web_socket"):
                await context.route_web_socket("**/*", lambda route: route.close())
            page = await context.new_page()
            page.set_default_timeout(10_000)
            response = await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            if not response or response.status >= 400:
                return _result("needs_input", "The application page is unavailable")
            await _public_target(page.url, allowed, test_origin=local_origin)
            if await page.locator(CAPTCHA).count():
                return _result("needs_input", "CAPTCHA, authentication, or MFA requires human intervention")
            inventory = await _field_inventory(page)
            if len(inventory) > MAX_FIELDS:
                return _result("needs_input", "Application has too many fields for the supported adapter")
            if is_test and await page.locator('form[data-internpilot-adapter="test-v1"]').count() != 1:
                return _result("needs_input", "The test application adapter could not be verified")
            issues: list[str] = []
            for index, field in enumerate(inventory):
                label = field["label"].strip().rstrip(" *:").lower()
                # Persist only the label and mapping status, never answers.
                record = {"label": field["label"][:160], "profile_field": None, "status": "unmapped"}
                fields.append(record)
                if field["disabled"] or field["readOnly"]:
                    record["status"] = "read_only"
                    if field["required"]:
                        issues.append("A required read-only question needs review")
                    continue
                # Inventory includes only visible controls. Select controls by a
                # stable matching id/name without CSS interpolation from job text.
                handles = await page.locator("input, select, textarea").element_handles()
                element = None
                for handle in handles:
                    attrs = await handle.evaluate("el => ({id:el.id,name:el.name,type:el.type,visible:!!el.getClientRects().length})")
                    if attrs["visible"] and attrs["id"] == field["id"] and attrs["name"] == field["name"] and attrs["type"] == field["type"]:
                        element = handle
                        break
                if element is None:
                    issues.append("The application changed while mapping its fields")
                    continue
                if SENSITIVE.search(label) or field["type"] in {"checkbox", "radio", "password"}:
                    record["status"] = "human_required"
                    issues.append("A sensitive or legally significant question requires human input")
                    continue
                if field["type"] == "file":
                    if label in {"resume", "resume (pdf)", "cv", "resume/cv"}:
                        if not is_test:
                            check = before_upload()
                            if inspect.isawaitable(check):
                                check = await check
                            if check is False:
                                return _result("needs_input", "Resume upload approval was revoked", fields=fields)
                        await element.set_input_files({"name": "resume.pdf", "mimeType": "application/pdf", "buffer": resume})
                        record.update(profile_field="resume", status="filled")
                    else:
                        record["status"] = "human_required"
                        issues.append("An unsupported document upload requires human input")
                    continue
                key = FIELD_MAP.get(label)
                value = profile.get(key) if key else None
                if key and key in verified and value is not None and str(value).strip():
                    record["profile_field"] = key
                    try:
                        if field["tag"] == "select":
                            options = await element.eval_on_selector_all("option", "els => els.map(o=>({value:o.value,label:o.label,disabled:o.disabled}))")
                            matches = [o for o in options if not o["disabled"] and (o["value"] == str(value) or o["label"] == str(value))]
                            if len(matches) != 1:
                                raise ValueError("No unique exact dropdown answer")
                            await element.select_option(value=matches[0]["value"])
                        else:
                            await element.fill(str(value))
                        record["status"] = "filled"
                    except (ValueError, PlaywrightError):
                        record["status"] = "human_required"
                        issues.append("A verified answer does not match the available form options")
                else:
                    record["status"] = "human_required"
                    issues.append("An unsupported question or missing verified profile fact requires human input")
            # Native HTML validity checks supplement mapping; no click is used to
            # discover invalid fields because some sites submit despite errors.
            valid = await page.locator("form").evaluate_all("els => els.length === 1 && els.every(f=>f.checkValidity())")
            screenshot = await page.screenshot(full_page=False, type="png")
            state = await context.storage_state()
            base = {"screenshot": screenshot, "fields": fields, "session_state": state}
            if issues or not valid:
                return _result("needs_input", issues[0] if issues else "Required fields failed browser validation", **base)
            if blocked_request:
                return _result("needs_input", "The page attempted a request outside its approved read-only access", **base)
            if not submit:
                if not is_test:
                    return _result("needs_input", "Verified static fields prepared; this employer requires manual completion on the official page", **base)
                return _result("awaiting_review", "Verified fields prepared; explicit approval is required before submission", **base)
            if before_submit is None:
                return _result("needs_input", "A final policy recheck is required before submission", **base)
            try:
                check = before_submit(screenshot)
                if inspect.isawaitable(check):
                    check = await check
                if check is False:
                    return _result("needs_input", "The final policy check blocked submission", **base)
            except Exception:
                return _result("needs_input", "The final policy check blocked submission", **base)
            # Mark attempted BEFORE the click. Every failure afterward is outcome
            # uncertainty, including a timeout; retrying could duplicate a success.
            attempted = True
            await page.get_by_role("button", name="Submit test application", exact=True).click()
            try:
                await page.locator("[data-internpilot-confirmation]").wait_for(state="visible", timeout=7000)
            except PlaywrightError:
                return _result("uncertain", "Submission was attempted but authoritative confirmation was not found; do not retry", **base)
            confirmation = await page.locator("[data-internpilot-confirmation]").get_attribute("data-internpilot-confirmation")
            await _public_target(page.url, allowed, test_origin=local_origin)
            if not confirmation or not re.fullmatch(r"TEST-[A-F0-9]{12}", confirmation):
                return _result("uncertain", "The confirmation identifier could not be validated; do not retry", **base)
            # Independent same-origin record proves that the PDF was received.
            record_response = await context.request.get(urljoin(url, f"/test-portal/records/{confirmation}"))
            record = await record_response.json()
            import hashlib
            if (record_response.status != 200 or record.get("id") != confirmation or
                    record.get("resume_sha256") != hashlib.sha256(resume).hexdigest()):
                return _result("uncertain", "The server confirmation did not verify the resume upload; do not retry", **base)
            base["session_state"] = await context.storage_state()
            return _result("submitted", "The authorized test endpoint confirmed application and document receipt",
                           confirmation_id=confirmation, confirmation_text=f"Application received: {confirmation}; resume upload verified", **base)
    except (PlaywrightError, OSError, ValueError, TimeoutError):
        return _result("uncertain" if attempted else "needs_input",
                       "Submission outcome is unknown; reconcile before any retry" if attempted else "Browser preparation failed; inspect worker configuration or complete manually",
                       screenshot=screenshot, fields=fields)
    finally:
        if context is not None:
            try:
                await context.close()
            except PlaywrightError:
                pass
        if browser is not None:
            try:
                await browser.close()
            except PlaywrightError:
                pass
