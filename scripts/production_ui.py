"""Production-upgrade UI acceptance, using isolated synthetic data only."""
import json
import os
import re
import secrets
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT=Path(__file__).resolve().parents[1]
if os.getenv("UI_TEST_ALLOW_OWNER_CLI")!="true" or "internpilot-ui-" not in os.getenv("DATABASE_URL",""):
    raise SystemExit("Run through run-ui-acceptance.py --production-ui with a fresh temporary database")
OUT=ROOT/"artifacts"
report={"at":datetime.now(UTC).isoformat(),"checks":[],"external_emails":0,"external_submissions":0,"synthetic_data_only":True}


def passed(name):
    report["checks"].append({"name":name,"passed":True})
    print(name+": passed",flush=True)


def navigate(page,name):
    expect(page.locator(".detail-sheet[data-state='closed']")).to_have_count(0)
    if page.viewport_size["width"]<=1024:
        page.get_by_role("button",name="Open navigation",exact=True).click()
    target=page.get_by_role("button",name=name,exact=True)
    if not target.is_visible() and name in {"Discovery sources","Application policies"}:
        page.get_by_role("button",name="Automation center",exact=True).click()
        if page.viewport_size["width"]<=1024:
            page.get_by_role("button",name="Open navigation",exact=True).click()
    target.click()


try:
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(executable_path=shutil.which("chromium"),headless=True,args=["--no-sandbox"])
        context=browser.new_context(viewport={"width":1440,"height":1050})
        page=context.new_page();page.set_default_timeout(20000)
        errors=[];page.on("pageerror",lambda error:errors.append(str(error)))
        base=os.getenv("UI_TEST_URL","http://127.0.0.1:3000")
        page.goto(base)
        assert context.request.get(base+"/api/health").json()["test_mode"]
        page.get_by_label("Email address",exact=True).fill("production-ui-"+secrets.token_hex(5)+"@example.test")
        page.get_by_label("Password",exact=False).fill(secrets.token_urlsafe(24))
        page.get_by_role("button",name="Create your workspace",exact=True).click()
        page.get_by_role("heading",name="Your opportunity notebook.").wait_for()
        session=context.request.get(base+"/api/auth/session").json()
        headers={"X-CSRF-Token":session["csrf_token"]}
        profile=context.request.get(base+"/api/profile").json()
        profile.update(name="Synthetic Product Tester",projects=[{"name":"Internship monitor","description":"Built a Python internship monitor with deduplication.","skills":["Python"]}],verified_fields=["name","projects","country","graduation_year"])
        assert context.request.put(base+"/api/profile",headers=headers,data=profile).status==200
        page.reload()
        page.get_by_role("heading",name="Your opportunity notebook.").wait_for()
        expect(page.locator(".account strong")).to_have_text("Synthetic Product Tester")
        passed("New account and verified factual project persist")
        navigate(page,"Recruiter outreach")
        page.get_by_role("heading",name="Recruiter outreach",exact=True).wait_for()
        expect(page.get_by_role("button",name="Connect Gmail",exact=True)).to_be_disabled()
        expect(page.get_by_text("Server setup needed:",exact=False)).to_be_visible()
        page.screenshot(path=str(OUT/"production-outreach-empty.png"),full_page=True)
        page.get_by_role("button",name="Add contact",exact=True).click()
        for label,value in (("Contact name","Synthetic Recruiter"),("Recruiter email","recruiter@example.invalid"),("Company","Synthetic Employer"),("Relevant role","Python internship"),("Contact source URL","https://example.invalid/recruiting")):
            page.get_by_label(label,exact=True).fill(value)
        page.get_by_role("checkbox",name="I verified the address",exact=False).check()
        page.get_by_role("button",name="Save contact",exact=True).click()
        expect(page.get_by_role("dialog")).to_have_count(0)
        page.get_by_role("button",name="Contacts",exact=True).click()
        page.get_by_role("button",name="Draft email",exact=True).click()
        expect(page.get_by_role("dialog")).to_be_visible()
        assert "deduplication" in page.get_by_label("Email body",exact=True).input_value()
        expect(page.get_by_role("button",name="Approve & queue",exact=True)).to_be_disabled()
        passed("Verified contact generates factual email; missing Gmail prevents approval")
        page.get_by_label("Email body",exact=True).fill("Hello Synthetic Recruiter,\n\nI built the verified Python internship monitor. Could you share the official application?\n\nSynthetic Product Tester")
        page.get_by_role("checkbox",name="I reviewed this exact recipient",exact=False).check()
        page.get_by_role("button",name="Save reviewed draft",exact=True).click()
        expect(page.get_by_label("Email body",exact=True)).to_have_value(re.compile("reply 'stop'"))
        page.get_by_role("button",name="Close dialog",exact=True).click()
        page.get_by_role("button",name="Review queue",exact=True).click()
        expect(page.locator(".quiet-table tbody tr")).to_have_count(1)
        page.screenshot(path=str(OUT/"production-outreach-desktop.png"),full_page=True)
        passed("Draft editing retains opt-out footer and requires fresh approval")
        page.get_by_role("button",name="Sender settings",exact=True).click()
        page.get_by_label("Daily maximum",exact=True).fill("40")
        page.get_by_label("Minimum gap (minutes)",exact=True).fill("20")
        page.get_by_role("button",name="Save sender settings",exact=True).click()
        page.get_by_role("status").filter(has_text="Sender settings saved").wait_for()
        snapshot=context.request.get(base+"/api/outreach").json()
        assert snapshot["settings"]["daily_limit"]==40 and not snapshot["settings"]["enabled"] and snapshot["counts"].get("sent",0)==0
        page.get_by_role("button",name="Contacts",exact=True).click()
        page.get_by_role("button",name="Opt out",exact=True).click()
        page.get_by_role("status").filter(has_text="Contact opted out").wait_for()
        assert context.request.get(base+"/api/outreach").json()["messages"][0]["status"]=="cancelled"
        passed("Sender limits save and opting out cancels unsent messages")
        navigate(page,"Automation center")
        page.get_by_role("heading",name="Automation center",exact=True).wait_for()
        page.get_by_role("heading",name="Operations",exact=True).wait_for()
        operations=context.request.get(base+"/api/operations").json()
        assert operations["sources"]>=6 and operations["worker"]["active_workers"]>=1
        page.screenshot(path=str(OUT/"production-automation-desktop.png"),full_page=True)
        passed("Automation center reflects real database workers and source configuration")
        navigate(page,"Discovery sources")
        configs=[{"kind":"greenhouse","slug":f"synthetic-ui-{i}","company":f"SYNTHETIC disabled source {i}","enabled":False,"permitted":False} for i in range(30)]
        assert context.request.post(base+"/api/sources/bulk",headers=headers,data={"sources":configs}).status==200
        navigate(page,"Overview");navigate(page,"Discovery sources")
        expect(page.locator(".source-row")).to_have_count(25,timeout=20000)
        page.get_by_role("button",name="Next",exact=True).click()
        expect(page.locator(".source-row")).to_have_count(11)
        page.get_by_label("Search sources",exact=True).fill("source 29")
        expect(page.locator(".source-row")).to_have_count(1)
        passed("Source manager searches and paginates real persisted configurations")
        navigate(page,"Application policies")
        page.get_by_role("button",name="Run local application test",exact=True).click()
        end=time.monotonic()+80
        local=None
        while time.monotonic()<end:
            rows=context.request.get(base+"/api/applications").json()
            local=next((row for row in rows if row.get("is_demo")),None)
            if local and local["status"] in {"submitted","failed","needs_input","uncertain"}:break
            page.wait_for_timeout(1000)
        assert local and local["status"]=="submitted" and local["confirmation_id"],local
        navigate(page,"Applications")
        expect(page.locator(".kanban-entry")).to_have_count(1)
        page.screenshot(path=str(OUT/"production-applications-desktop.png"),full_page=True)
        page.get_by_role("button",name="List",exact=True).click()
        expect(page.locator(".application-row")).to_have_count(1)
        page.get_by_role("button",name="Board",exact=True).click()
        page.locator(".kanban-entry").click()
        page.get_by_role("heading",name="Application record",exact=True).wait_for()
        page.get_by_role("button",name="Close dialog",exact=True).click()
        passed("Kanban/list and detail show a real authorized local confirmation")
        navigate(page,"Resume studio")
        expect(page.get_by_role("link",name="Download",exact=True).first).to_be_visible()
        navigate(page,"Overview")
        page.screenshot(path=str(OUT/"production-overview-desktop.png"),full_page=True)
        for width in (390,768,1024):
            page.set_viewport_size({"width":width,"height":900})
            expect(page.locator(".sidebar")).not_to_be_in_viewport()
            assert page.evaluate("document.documentElement.scrollWidth<=window.innerWidth"),f"Page overflow at {width}"
            navigate(page,"Recruiter outreach")
            page.get_by_role("heading",name="Recruiter outreach",exact=True).wait_for()
            assert page.evaluate("document.documentElement.scrollWidth<=window.innerWidth"),f"Outreach overflow at {width}"
            if width==390:
                page.get_by_label("Color theme",exact=True).select_option("dark")
                page.wait_for_timeout(250)  # Let the purposeful color transition settle for the screenshot.
                page.evaluate("window.scrollTo(0,0)")
                page.screenshot(path=str(OUT/"production-outreach-mobile-dark.png"),full_page=True)
                page.get_by_label("Color theme",exact=True).select_option("light")
                navigate(page,"Applications")
                page.screenshot(path=str(OUT/"production-applications-mobile.png"),full_page=True)
        passed("Responsive floating navigation, outreach and board at 390/768/1024px")
        page.get_by_role("button",name="Sign out",exact=True).click()
        page.get_by_label("Email address",exact=True).wait_for()
        page.get_by_label("Email address",exact=True).fill("second-"+secrets.token_hex(5)+"@example.test")
        page.get_by_label("Password",exact=False).fill(secrets.token_urlsafe(24))
        page.get_by_role("button",name="Create your workspace",exact=True).click()
        page.get_by_role("heading",name="Your opportunity notebook.").wait_for()
        expect(page.locator(".account strong")).to_have_text("Your profile")
        navigate(page,"Recruiter outreach")
        assert context.request.get(base+"/api/outreach").json()["contacts"]==[]
        expect(page.locator(".quiet-table tbody tr")).to_have_count(0)
        passed("Account switch clears private panels and does not retain previous contacts")
        assert not errors,errors
        passed("No JavaScript errors with production CSP")
        browser.close()
    report["passed"]=True
except Exception as exc:
    report["passed"]=False;report["failure"]=str(exc)[:2000]
    raise
finally:
    (OUT/"production-ui.json").write_text(json.dumps(report,indent=2)+"\n")
