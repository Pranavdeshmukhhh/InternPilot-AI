"""An isolated, explicitly enabled application target for browser acceptance tests.

The application must mount this router only when TEST_MODE is enabled. It accepts
synthetic candidate data; no request is forwarded to an employer.
"""
from __future__ import annotations

import hashlib
import html
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/test-portal", tags=["test portal"])
__test__ = False
MAX_UPLOAD = 8 * 1024 * 1024


def _connection() -> sqlite3.Connection:
    directory = Path(os.getenv("DATA_DIR", "./data"))
    directory.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(directory / "test-portal.sqlite3", timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("""CREATE TABLE IF NOT EXISTS submissions (
        id TEXT PRIMARY KEY, dedupe_key TEXT UNIQUE NOT NULL,
        created_at TEXT NOT NULL, resume_sha256 TEXT NOT NULL,
        resume_bytes INTEGER NOT NULL, filename TEXT NOT NULL)""")
    return db


def _page(body: str) -> HTMLResponse:
    return HTMLResponse(f"""<!doctype html><html lang="en"><head>
    <meta charset="utf-8"><meta name="viewport" content="width=device-width">
    <title>InternPilot authorized test application</title>
    <style>body{{font:16px system-ui,sans-serif;background:#f5f7fa;color:#18212f;
    max-width:680px;margin:48px auto;padding:24px}}main{{background:white;padding:32px;
    border:1px solid #dce3eb;border-radius:12px}}label{{display:block;margin:18px 0 6px}}
    input,select,textarea{{box-sizing:border-box;width:100%;padding:10px;font:inherit;
    border:1px solid #b5c1cf;border-radius:6px}}button{{margin-top:24px;padding:12px 20px;
    background:#12553d;color:white;border:0;border-radius:6px;font:inherit}}
    .banner{{padding:12px;background:#fff6ce;border-radius:6px}}</style></head><body>
    <main><p class="banner">Authorized local test endpoint. Synthetic data only.</p>{body}</main>
    </body></html>""")


@router.get("/apply", response_class=HTMLResponse)
async def application_form(variant: str = "normal") -> HTMLResponse:
    if variant not in {"normal", "ambiguous", "captcha", "no-confirmation"}:
        raise HTTPException(400, "Unsupported test variant")
    extra = ""
    if variant == "ambiguous":
        extra = '<label for="sponsorship">Will you require visa sponsorship?</label><select id="sponsorship" name="sponsorship" required><option value="">Choose</option><option>Yes</option><option>No</option></select>'
    if variant == "captcha":
        extra = '<div class="g-recaptcha" data-sitekey="test">CAPTCHA: human intervention required</div>'
    token = str(uuid.uuid4())
    return _page(f"""<h1>Software Engineering Internship</h1>
    <p>2029 undergraduate program · India · Test requisition TEST-2029</p>
    <form action="/test-portal/submit" method="post" enctype="multipart/form-data" data-internpilot-adapter="test-v1">
    <input type="hidden" name="request_token" value="{token}">
    <input type="hidden" name="variant" value="{html.escape(variant)}">
    <label for="full_name">Full name</label><input id="full_name" name="full_name" autocomplete="name" required>
    <label for="email">Email address</label><input id="email" name="email" type="email" required>
    <label for="country">Country</label><select id="country" name="country" required>
    <option value="">Choose</option><option>India</option><option>United States</option><option>United Kingdom</option></select>
    <label for="graduation_year">Expected graduation year</label><select id="graduation_year" name="graduation_year" required>
    <option value="">Choose</option>{''.join(f'<option>{y}</option>' for y in range(2026, 2033))}</select>
    <label for="resume">Resume (PDF)</label><input id="resume" name="resume" type="file" accept="application/pdf" required>
    {extra}<button type="submit">Submit test application</button></form>""")


@router.post("/submit", response_class=HTMLResponse)
async def submit_application(
    full_name: str = Form(...), email: str = Form(...), country: str = Form(...),
    graduation_year: int = Form(...), request_token: str = Form(...),
    variant: str = Form("normal"), resume: UploadFile = File(...),
) -> HTMLResponse:
    if not full_name.strip() or "@" not in email or country != "India" or graduation_year != 2029:
        raise HTTPException(422, "The local fixture accepts a verified India / 2029 test candidate only")
    try:
        uuid.UUID(request_token)
    except ValueError as exc:
        raise HTTPException(422, "Invalid request token") from exc
    content = await resume.read(MAX_UPLOAD + 1)
    if not content.startswith(b"%PDF-") or len(content) > MAX_UPLOAD:
        raise HTTPException(422, "A PDF resume of at most 8 MiB is required")
    # Do not store contact information or uploaded resume bytes in this test service.
    key = hashlib.sha256(f"TEST-2029:{email.strip().lower()}".encode()).hexdigest()
    with _connection() as db:
        db.execute(
            "INSERT OR IGNORE INTO submissions VALUES (?, ?, ?, ?, ?, ?)",
            (f"TEST-{uuid.uuid4().hex[:12].upper()}", key, datetime.now(timezone.utc).isoformat(),
             hashlib.sha256(content).hexdigest(), len(content), "resume.pdf"),
        )
        row = db.execute("SELECT * FROM submissions WHERE dedupe_key = ?", (key,)).fetchone()
    if variant == "no-confirmation":
        # Deliberately committed, but no confirmation is returned. The worker must
        # record uncertainty and must NOT retry this case automatically.
        return _page("<h1>Your request is being processed</h1><p>Confirmation unavailable.</p>")
    return _page(f'<h1 data-internpilot-confirmation="{row["id"]}">Application received</h1>'
                 f'<p>Application ID: <strong id="application-id">{row["id"]}</strong></p>'
                 '<p id="upload-confirmed">Resume upload verified.</p>')


@router.get("/records/{confirmation_id}")
async def submission_record(confirmation_id: str) -> dict:
    with _connection() as db:
        row = db.execute("SELECT * FROM submissions WHERE id = ?", (confirmation_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Test confirmation not found")
    return {k: row[k] for k in ("id", "created_at", "resume_sha256", "resume_bytes", "filename")}
