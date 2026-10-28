"""Browser checks against the isolated runner's temporary test database only."""
import json
import os
import secrets
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
if os.getenv("UI_TEST_ALLOW_OWNER_CLI")!="true" or "internpilot-ui-" not in os.getenv("DATABASE_URL",""):
    raise SystemExit("Use run-ui-acceptance.py --regional; a fresh temporary database is required.")
sys.path.insert(0,str(ROOT/"backend"))
from app.database import SessionLocal
from app.models import Opportunity, Source, SourceOpportunity
from app.security import digest
from app.services import canonical_fingerprint

OUT = ROOT/"artifacts"
report = {"at":datetime.now(UTC).isoformat(),"synthetic_data_only":True,"checks":[],"external_submissions":0}


def checked(name):
    report["checks"].append({"name":name,"passed":True})
    print(name+": passed",flush=True)


try:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=shutil.which("chromium"),headless=True,args=["--no-sandbox"])
        context = browser.new_context(viewport={"width":1440,"height":1050})
        page = context.new_page()
        errors = []
        page.on("pageerror",lambda exc:errors.append(str(exc)))
        base = os.getenv("UI_TEST_URL","http://127.0.0.1:3000")
        page.goto(base)
        assert context.request.get(base+"/api/health").json()["test_mode"]
        page.get_by_label("Email address",exact=True).fill("regional-"+secrets.token_hex(5)+"@example.test")
        page.get_by_label("Password",exact=False).fill(secrets.token_urlsafe(24))
        page.get_by_role("button",name="Create your workspace",exact=True).click()
        page.get_by_role("heading",name="Your opportunity notebook.").wait_for()
        session = context.request.get(base+"/api/auth/session").json()
        with SessionLocal() as db:
            source = Source(owner_id=session["user"]["id"],kind="test",slug="regional-synthetic",company="SYNTHETIC regional browser fixture",enabled=False,permitted=False)
            db.add(source); db.flush()
            for kind in ("internship","hackathon"):
                for index,place in enumerate(("Nagpur","Hinjawadi","Bengaluru","Berlin","Remote","Worldwide","Mumbai")):
                    data = {"title":f"SYNTHETIC {kind} in {place}","company":"Synthetic Regional Fixture","url":f"https://synthetic.example.invalid/{kind}/{index}",
                            "location":place,"remote":place in {"Remote","Worldwide"},"opportunity_type":kind,"description":"Synthetic local browser fixture. Verify eligibility.",
                            "source":"local_test","is_demo":True,"active":True,"registration_status":"unknown"}
                    job = Opportunity(fingerprint=digest(source.owner_id+canonical_fingerprint(data)),data=data)
                    db.add(job); db.flush(); db.add(SourceOpportunity(source_id=source.id,opportunity_id=job.id))
            db.commit()
        checked("Isolated labeled fixtures for internships and hackathons")
        for navigation in ("Internship explorer","Hackathon explorer"):
            page.get_by_role("button",name=navigation,exact=True).click()
            expect(page.locator(".results-bar strong")).to_have_text("7")
            for label,count in (("Near my cities",2),("Across India",4),("International",1),("Worldwide location",1),("Location unknown",1)):
                page.get_by_role("button",name=label,exact=True).click()
                expect(page.locator(".results-bar strong")).to_have_text(str(count))
                if label=="International":
                    expect(page.locator(".job-card")).to_contain_text("Berlin")
            page.get_by_role("button",name="Near my cities",exact=True).click()
            page.get_by_role("button",name="Pune",exact=True).click()
            expect(page.locator(".results-bar strong")).to_have_text("1")
            expect(page.locator(".job-card")).to_contain_text("Hinjawadi")
            page.get_by_role("button",name="Nagpur",exact=True).click()
            expect(page.locator(".job-card")).to_contain_text("Nagpur")
            checked(navigation+" region filters and individual local city controls")
        page.get_by_text("Local places & discovery coverage",exact=True).click()
        page.get_by_label("Your local cities",exact=True).fill("Mumbai, Pune")
        page.get_by_role("button",name="Save local preferences",exact=True).click()
        page.get_by_text("Local preferences saved.",exact=True).wait_for()
        page.get_by_role("button",name="Mumbai",exact=True).wait_for()
        page.get_by_role("button",name="All my local cities",exact=True).click()
        expect(page.locator(".results-bar strong")).to_have_text("2")
        page.get_by_label("Include named nearby places",exact=True).uncheck()
        page.get_by_role("button",name="Save local preferences",exact=True).click()
        expect(page.locator(".results-bar strong")).to_have_text("1")
        facts = context.request.get(base+"/api/profile").json()
        assert facts["preferred_local_cities"]==["Mumbai","Pune"] and facts["include_nearby_locations"] is False
        page.reload()
        page.get_by_role("heading",name="Your opportunity notebook.").wait_for()
        page.get_by_role("button",name="Hackathon explorer",exact=True).click()
        page.get_by_role("button",name="Near my cities",exact=True).click()
        page.get_by_role("button",name="Mumbai",exact=True).wait_for()
        expect(page.locator(".results-bar strong")).to_have_text("1")
        checked("Edited local cities and nearby preference persist after reload")
        page.get_by_text("Local places & discovery coverage",exact=True).click()
        expect(page.get_by_text("Broader local and international web search needs",exact=False)).to_be_visible()
        expect(page.get_by_role("button",name="Enable regional search sources",exact=True)).to_have_count(0)
        page.get_by_text("View regional search queries",exact=True).click()
        queries = context.request.get(base+"/api/discovery/regions").json()["search_presets"]
        expect(page.locator(".regional-query-list li")).to_have_count(len(queries))
        labels = " ".join(query["company"].lower() for query in queries)
        assert all(lane in labels for lane in ("mumbai", "pune", "india", "international", "remote"))
        assert "hackathon" in labels and "internship" in labels
        checked("Missing search key and actual query coverage are disclosed")
        page.get_by_label("Your local cities",exact=True).fill("Nagpur, Pune")
        page.get_by_label("Include named nearby places",exact=True).check()
        page.get_by_role("button",name="Save local preferences",exact=True).click()
        page.get_by_role("button",name="Nagpur",exact=True).wait_for()
        expect(page.locator(".results-bar strong")).to_have_text("2")
        page.get_by_text("Local places & discovery coverage",exact=True).click()
        page.evaluate("window.scrollTo(0,0)")
        page.screenshot(path=str(OUT/"regional-desktop.png"),full_page=True)
        page.set_viewport_size({"width":390,"height":844})
        expect(page.locator(".sidebar")).not_to_be_in_viewport()
        assert page.evaluate("document.documentElement.scrollWidth<=window.innerWidth"),"Mobile page overflows"
        page.screenshot(path=str(OUT/"regional-mobile.png"),full_page=True)
        checked("Responsive regional controls at 390px and desktop screenshots")
        assert not errors,errors
        checked("No browser JavaScript errors")
        browser.close()
    report["passed"] = True
except Exception as exc:
    report["passed"] = False
    report["failure"] = str(exc)[:2000]
    raise
finally:
    (OUT/"regional-ui.json").write_text(json.dumps(report,indent=2)+"\n")
