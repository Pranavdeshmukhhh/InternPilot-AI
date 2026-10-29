"""Offline product validation against fresh synthetic data and a production build."""
import json
import os
import secrets
import re
import shutil
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT=Path(__file__).resolve().parents[1]
if os.getenv('UI_TEST_ALLOW_OWNER_CLI')!='true' or 'internpilot-ui-' not in os.getenv('DATABASE_URL',''):
    raise SystemExit('Use scripts/run-ui-acceptance.py --phase6-ui with isolated data')
sys.path.insert(0,str(ROOT/'backend'))
from app.database import SessionLocal
from app.models import Opportunity,Source,SourceOpportunity
from app.security import digest

BASE=os.getenv('UI_TEST_URL','http://127.0.0.1:3000')
BEFORE=os.getenv('PHASE6_BASELINE')=='true'
OUT=Path(os.getenv('UI_ARTIFACT_DIR',str(ROOT/'artifacts'/('phase6-before' if BEFORE else 'phase6-after'))))
OUT.mkdir(parents=True,exist_ok=True)
report={'at':datetime.now(UTC).isoformat(),'baseline':BEFORE,'synthetic_only':True,'external_submissions':0,'external_emails':0,'crawl_workers':0,'checks':[],'vitals':[],'accessibility':[]}

def check(name):
    report['checks'].append({'name':name,'passed':True});print(name+': passed',flush=True)

def screenshot(page,name):
    page.screenshot(path=str(OUT/(name+'.png')),full_page=False,animations='disabled')

def compact_audit(page,axe):
    page.evaluate(axe)
    result=page.evaluate("""async()=>{const r=await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa','wcag22aa']}});return r.violations.map(v=>({id:v.id,impact:v.impact,description:v.description,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))}));}""")
    return result

def ready(page):
    try:
        page.get_by_role('heading',name='Your opportunity notebook.' if BEFORE else 'A clearer next step.',exact=True).wait_for()
    except Exception:
        screenshot(page,'failure')
        print(page.locator('body').inner_text()[:4500],flush=True)
        raise

try:
 with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=shutil.which('chromium'),headless=True,args=['--no-sandbox'])
    context=browser.new_context(viewport={'width':1440,'height':1000},color_scheme='dark')
    context.expose_binding('recordVital',lambda source,value:report['vitals'].append(value))
    context.add_init_script("""window.__ux={lcp:0,cls:0,interactions:[]};try{new PerformanceObserver(l=>{for(const e of l.getEntries())window.__ux.lcp=e.startTime;}).observe({type:'largest-contentful-paint',buffered:true});new PerformanceObserver(l=>{for(const e of l.getEntries())if(!e.hadRecentInput)window.__ux.cls+=e.value;}).observe({type:'layout-shift',buffered:true});new PerformanceObserver(l=>{for(const e of l.getEntries())if(e.interactionId)window.__ux.interactions.push(e.duration);}).observe({type:'event',buffered:true,durationThreshold:16});}catch{}window.addEventListener('internpilot:performance',e=>window.recordVital(e.detail));""")
    page=context.new_page();page.set_default_timeout(20000)
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    requests=[];page.on('request',lambda req:requests.append(req.url.split('/api',1)[-1]) if '/api/' in req.url and '/events/stream' not in req.url else None)
    page.goto(BASE+'/register');expect(page.locator('html')).to_have_attribute('data-theme','light')
    first_email='ux-'+secrets.token_hex(6)+'@example.invalid';first_password=secrets.token_urlsafe(24)
    page.get_by_label('Email address',exact=True).fill(first_email)
    page.get_by_label('Password',exact=False).fill(first_password)
    page.get_by_role('button',name='Create your workspace',exact=True).click()
    ready(page)
    account=context.request.get(BASE+'/api/auth/session').json();owner=account['user']['id']
    with SessionLocal() as db:
        source=Source(owner_id=owner,kind='test',company='Fictional UX fixtures',enabled=False,permitted=False)
        db.add(source);db.flush()
        now=datetime.now(UTC)
        for i in range(29):
            title=('Research Engineer Intern' if i==0 else 'Software Engineering Intern' if i%3==0 else 'Cloud Engineering Intern' if i%3==1 else 'Machine Learning Intern') if i<26 else 'Student AI Hackathon'
            data={'title':title+(' · Research systems, reliable cloud infrastructure and international student collaboration' if i==4 else ''),'company':['Example Research','Example Studio','Example Systems'][i%3], 'location':['Pune, India','Nagpur, India','Remote · India','Berlin, Germany'][i%4], 'remote':i%2==0, 'url':f'https://fictional.example.invalid/role/{i}', 'opportunity_type':'internship' if i<26 else 'hackathon','registration_status':'open','skills':['Python','SQL'],'description':'Fictional, labeled UI acceptance record. Currently pursuing an undergraduate degree, graduating in 2029. Work on reliable software with a research team. Python and SQL.','deadline':(now+timedelta(days=3+i)).isoformat(),'published_at':(now-timedelta(hours=i)).isoformat(),'source':'local_test','is_demo':True,'active':True}
            row=Opportunity(fingerprint=digest(owner+str(i)),data=data);db.add(row);db.flush();db.add(SourceOpportunity(source_id=source.id,opportunity_id=row.id))
        db.commit()
    page.reload();ready(page)
    if BEFORE:page.get_by_role('button',name='Internship explorer',exact=True).click()
    else:page.get_by_role('link',name='Explore',exact=True).first.click()
    expect(page.locator('.job-card')).to_have_count(20)
    report['row_height']=page.locator('.studio-opportunity').first.bounding_box()['height']
    screenshot(page,'explorer-desktop')
    start=len(requests);page.wait_for_timeout(17000)
    report['idle_17s_requests']=dict(Counter(requests[start:]));report['idle_17s_total']=len(requests)-start
    report['browser_observers']=page.evaluate('window.__ux')
    report['resources']=page.evaluate(r"""()=>performance.getEntriesByType('resource').filter(r=>/\.(js|css)(\?|$)/.test(r.name)).map(r=>({path:new URL(r.name).pathname,encoded:r.encodedBodySize,decoded:r.decodedBodySize,transfer:r.transferSize}))""")
    report['js_decoded_bytes']=sum(r['decoded'] for r in report['resources'] if '.js' in r['path'])
    report['js_encoded_bytes']=sum(r['encoded'] for r in report['resources'] if '.js' in r['path'])
    if BEFORE:
        check('Audited baseline renders actual synthetic listings and records idle request count')
    else:
        assert report['idle_17s_total']<=2,report['idle_17s_requests']
        check('Active explorer does not refresh unrelated dashboard/documents/sources on an idle timer')
        assert report['row_height']<=135,report['row_height']
        assert '/v2/opportunities?' in ' '.join(requests)
        check('Compact explorer uses bounded cursor projections')
        page.keyboard.press('/');expect(page.get_by_label('Search opportunities',exact=True)).to_be_focused()
        page.get_by_label('Search opportunities',exact=True).fill('Research Engineer')
        expect(page.locator('.job-card')).to_have_count(1)
        page.get_by_role('button',name='Clear search',exact=True).click();expect(page.locator('.job-card')).to_have_count(20)
        page.get_by_role('button',name='Next',exact=True).click();expect(page.locator('.job-card')).to_have_count(6)
        page.get_by_role('button',name='Previous',exact=True).click();expect(page.locator('.job-card')).to_have_count(20)
        check('Debounced search and forward/back cursor pages return real results')
        first=page.locator('.job-card').first;title=first.locator('h3').inner_text();first.click()
        dialog=page.get_by_role('dialog');expect(dialog.get_by_role('heading',name=title,exact=True)).to_be_visible()
        expect(dialog.get_by_text('Verified requirements',exact=True)).to_be_visible()
        assert 'opportunity=' in page.url
        screenshot(page,'detail-desktop')
        page.keyboard.press('Tab');assert dialog.evaluate('el=>el.contains(document.activeElement)')
        page.go_back();expect(dialog).to_have_count(0)
        first=page.locator('.job-card').first;first.click();expect(dialog).to_be_visible();page.keyboard.press('Escape');expect(dialog).to_have_count(0);expect(first).to_be_focused()
        check('Detail URLs, browser back, focus trap and Escape remain functional')
        page.get_by_role('button',name=f'Save {title}',exact=True).click()
        expect(page.get_by_role('button',name=f'Unsave {title}',exact=True)).to_have_attribute('aria-pressed','true')
        page.get_by_role('link',name='Saved',exact=True).click();expect(page.locator('.job-card')).to_have_count(1)
        page.reload();expect(page.locator('.job-card')).to_have_count(1)
        check('Save persists through navigation and reload')
        page.keyboard.press('Control+k');expect(page.get_by_label('Search workspace',exact=True)).to_be_focused()
        page.get_by_label('Search workspace',exact=True).fill('Hackathons');page.keyboard.press('Enter')
        expect(page.get_by_role('heading',name='Hackathons',exact=True)).to_be_visible();expect(page.locator('.job-card')).to_have_count(3)
        check('Global keyboard command search navigates to hackathons')
        page.get_by_role('link',name='Internships',exact=True).click();expect(page.locator('.job-card')).to_have_count(20)
        page.get_by_role('button',name='Filters',exact=True).click();dialog=page.get_by_role('dialog')
        dialog.get_by_label('Company or organizer',exact=True).fill('No such employer')
        dialog.get_by_role('button',name='Cancel',exact=True).click();expect(page.locator('.job-card')).to_have_count(20)
        page.get_by_role('button',name='Filters',exact=True).click()
        dialog.get_by_label('Location',exact=True).fill('Pune');dialog.get_by_role('button',name='Apply filters',exact=True).click()
        expect(page.locator('.job-card')).to_have_count(7)
        page.reload();expect(page.locator('.job-card')).to_have_count(7)
        check('Filter dialog cancels drafts and persists applied filters in the URL')
        page.get_by_role('button',name='Filters',exact=True).click();dialog.get_by_role('button',name='Reset filters',exact=True).click();dialog.get_by_role('button',name='Apply filters',exact=True).click()
        expect(page.locator('.job-card')).to_have_count(20)
        axe=(ROOT/'frontend/node_modules/axe-core/axe.min.js').read_text()
        for theme in ['light','dark']:
            page.get_by_label('Color theme',exact=True).select_option(theme)
            expect(page.locator('html')).to_have_attribute('data-theme',theme)
            page.wait_for_timeout(180)
            violations=compact_audit(page,axe);report['accessibility'].append({'view':'explorer','theme':theme,'violations':violations})
            assert not [v for v in violations if v['impact'] in ['serious','critical']],violations
            screenshot(page,'explorer-'+theme)
        check('Explorer automated WCAG checks have no serious/critical findings in both themes')
        for width in [320,390,768,1024,1440,1920]:
            page.set_viewport_size({'width':width,'height':900});page.evaluate('window.scrollTo(0,0)')
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),f'overflow at {width}'
            if width in [320,390,768]:screenshot(page,f'explorer-{width}')
        page.set_viewport_size({'width':390,'height':844});page.get_by_role('button',name='Open navigation',exact=True).click()
        dialog=page.get_by_role('dialog');expect(dialog.get_by_role('navigation',name='Main navigation')).to_be_visible()
        page.keyboard.press('Tab');assert dialog.evaluate('el=>el.contains(document.activeElement)')
        dialog.get_by_role('link',name='Applications',exact=True).click();expect(dialog).to_have_count(0)
        expect(page.get_by_role('heading',name='Applications',exact=True)).to_be_visible();screenshot(page,'applications-mobile')
        check('Mobile navigation traps focus, closes after navigation and layouts reflow from 320–1920px')
        page.goto(BASE+'/settings/profile');page.get_by_label('Full name',exact=True).fill('Synthetic Candidate')
        page.wait_for_timeout(2500);expect(page.get_by_label('Full name',exact=True)).to_have_value('Synthetic Candidate')
        screenshot(page,'profile-mobile')
        check('Profile edits remain intact through background workspace activity')
        page.goto(BASE+'/documents');expect(page.get_by_role('heading',name='Resume studio',exact=True)).to_be_visible();screenshot(page,'documents-mobile')
        page.goto(BASE+'/automation');expect(page.get_by_role('heading',name='Automation center',exact=True)).to_be_visible();screenshot(page,'automation-mobile')
        page.goto(BASE+'/outreach');page.get_by_role('heading',name='Recruiter outreach',exact=True).wait_for();screenshot(page,'outreach-mobile')
        page.goto(BASE+'/overview');page.get_by_role('heading',name='A clearer next step.',exact=True).wait_for();screenshot(page,'overview-mobile')
        page.set_viewport_size({'width':1440,'height':1000});screenshot(page,'overview-desktop')
        page.emulate_media(reduced_motion='reduce')
        assert page.locator('.btn').first.evaluate('el=>getComputedStyle(el).transitionDuration')=='0s'
        assert not errors,errors
        check('Documents, outreach, automation, profile, overview and reduced motion render without JavaScript errors')
        # Broader real workflows: facts stay verified, documents are actual PDFs,
        # application preparation remains queued without a crawler/browser worker.
        page.goto(BASE+'/settings/profile')
        fields={'Full name':'Synthetic Candidate','Application email':'candidate@example.invalid','University / institution':'Example University','Degree / program':'B.Tech Computer Science'}
        for label,value in fields.items():
            field=page.get_by_label(label,exact=True);field.fill(value)
            page.locator('.verified-field').filter(has=field).get_by_role('checkbox').check()
        skills=page.get_by_label(re.compile('^Verified technical skills'));skills.fill('Python, SQL')
        page.locator('.verified-field').filter(has=skills).get_by_role('checkbox').check()
        page.get_by_role('button',name='Save verified profile',exact=True).click()
        expect(page.get_by_text('Profile saved. Only your verified facts are used.',exact=True)).to_be_visible()
        page.goto(BASE+'/documents');page.get_by_role('heading',name='Resume studio',exact=True).wait_for()
        target=page.get_by_label('Target opportunity',exact=False);target.select_option(index=1)
        page.get_by_role('button',name='Generate PDF',exact=True).click()
        expect(page.locator('.quiet-table tbody tr')).to_have_count(1)
        with page.expect_download() as download:
            page.get_by_role('link',name='Download',exact=False).first.click()
        artifact=download.value
        assert Path(artifact.path()).read_bytes().startswith(b'%PDF-')
        check('Profile verification and document generation/download use actual API records and a real PDF')
        page.goto(BASE+'/automation/policies')
        page.locator('.mode-card').filter(has_text='Assisted Apply').get_by_role('radio').check()
        page.get_by_role('button',name='Save application policies',exact=True).click()
        expect(page.get_by_text('Application policies saved.',exact=True)).to_be_visible()
        page.goto(BASE+'/explore/internships');page.locator('.job-card').first.click()
        dialog=page.get_by_role('dialog');expect(dialog).to_be_visible()
        dialog.get_by_role('button',name='Prepare draft application',exact=True).click()
        expect(page.get_by_text('Draft preparation queued. Review its progress in Applications.',exact=True)).to_be_visible()
        expect(dialog.get_by_role('button',name='Already in applications',exact=True)).to_be_disabled()
        page.keyboard.press('Escape');expect(dialog).to_have_count(0)
        page.goto(BASE+'/applications')
        expect(page.locator('.kanban-entry')).to_have_count(1)
        expect(page.locator('.kanban-entry')).to_contain_text('queued')
        assert not page.get_by_text('Confirmation:',exact=False).count()
        check('Application preparation creates one queued record and never claims submission')
        page.goto(BASE+'/notifications')
        page.get_by_role('heading',name='Notification preferences',exact=True).wait_for()
        recipient=page.get_by_label('Time zone',exact=False)
        recipient.fill('Europe/London')
        # A real owner-scoped event refresh rerenders Workspace; it must not reset a dirty settings form.
        with SessionLocal() as db:
            from app.services import event
            event(db,owner,'ux_fixture','Synthetic UI event',notify=True);db.commit()
        page.wait_for_timeout(1800);expect(recipient).to_have_value('Europe/London')
        check('Event-driven notification updates preserve unsaved notification preferences')
        # Headless Chromium does not consistently hide inactive tabs. Simulate
        # the Page Visibility signal explicitly; do not claim a device test.
        page.evaluate("""()=>{Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});document.dispatchEvent(new Event('visibilitychange'));}""")
        hidden_start=len(requests)
        with SessionLocal() as db:
            event(db,owner,'ux_background','Synthetic background update',notify=True);db.commit()
        page.wait_for_timeout(2200)
        assert len(requests)==hidden_start,requests[hidden_start:]
        page.evaluate("""()=>{delete document.hidden;document.dispatchEvent(new Event('visibilitychange'));}""")
        expect(page.get_by_text('Synthetic background update',exact=True)).to_be_visible()
        expect(recipient).to_have_value('Europe/London')
        check('Simulated page visibility defers event refresh and catches up without resetting dirty fields')
        page.goto(BASE+'/automation/sources');page.get_by_role('heading',name='Discovery sources',exact=True).wait_for()
        page.get_by_text('Locations, source catalog & publisher review',exact=True).click()
        page.get_by_text('Local places & discovery coverage',exact=True).click()
        expect(page.get_by_label('Your local cities',exact=False)).to_be_visible()
        page.get_by_role('button',name='Add a source',exact=True).click()
        dialog=page.get_by_role('dialog');expect(dialog).to_be_visible()
        dialog.get_by_label('Company / source name',exact=True).fill('UI-only source')
        dialog.get_by_label('Board slug',exact=True).fill('synthetic')
        dialog.get_by_label(re.compile('^I confirm this public API')).check()
        dialog.get_by_label('Enable scheduled discovery',exact=True).uncheck()
        dialog.get_by_role('button',name='Save source',exact=True).click();expect(dialog).to_have_count(0)
        page.get_by_role('button',name='Remove UI-only source',exact=True).click();expect(dialog).to_be_visible()
        dialog.get_by_role('button',name='Remove source',exact=True).click();expect(dialog).to_have_count(0)
        expect(page.get_by_role('button',name='Remove UI-only source',exact=True)).to_have_count(0)
        check('Relocated discovery preferences and source create/delete use real APIs without a crawl worker')

        for route in ['/overview','/applications','/documents','/settings/profile','/automation','/notifications','/outreach']:
            page.goto(BASE+route);page.locator('main h1').wait_for();page.wait_for_timeout(200)
            violations=compact_audit(page,axe)
            report['accessibility'].append({'view':route,'theme':'dark','violations':violations})
            assert not [v for v in violations if v['impact'] in ['serious','critical']],violations
        check('Core feature screens pass serious/critical automated accessibility gates')
        page.goto(BASE+'/settings/security');page.locator('main h1').wait_for()
        violations=compact_audit(page,axe);report['accessibility'].append({'view':'security','theme':'dark','violations':violations})
        assert not [v for v in violations if v['impact'] in ['serious','critical']],violations
        result=subprocess.run([sys.executable,'-c',"from app.admin import main; import sys; raise SystemExit(main(['grant-owner',sys.argv[1]]))",first_email],cwd=ROOT/'backend',env=os.environ.copy(),capture_output=True,text=True)
        assert result.returncode==0,'Local owner fixture setup failed'
        page.goto(BASE+'/owner');page.get_by_role('button',name='Sign in',exact=True).click()
        page.get_by_label('Email address',exact=True).fill(first_email);page.get_by_label('Password',exact=False).fill(first_password)
        page.get_by_role('button',name='Sign in',exact=True).click();page.get_by_role('heading',name=re.compile('Good to see you')).wait_for()
        page.goto(BASE+'/owner');page.get_by_role('heading',name='Owner’s desk',exact=True).wait_for()
        screenshot(page,'owner-desktop')
        violations=compact_audit(page,axe);report['accessibility'].append({'view':'owner','theme':'dark','violations':violations})
        assert not [v for v in violations if v['impact'] in ['serious','critical']],violations
        check('Security and owner screens render access-controlled workflows with no serious/critical accessibility findings')
        # A fresh touch context checks actual coarse-pointer targets, not just a narrow desktop window.
        mobile=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True,device_scale_factor=2,storage_state=context.storage_state(),color_scheme='light')
        mobile_page=mobile.new_page();mobile_page.set_default_timeout(20000)
        mobile_page.goto(BASE+'/explore/internships');expect(mobile_page.locator('.job-card')).to_have_count(20)
        assert mobile_page.get_by_role('button',name=re.compile('^(Unsave|Save) ')).first.bounding_box()['width']>=44
        mobile_page.get_by_label('Color theme',exact=True).select_option('light')
        screenshot(mobile_page,'touch-explorer-light')
        mobile_page.locator('.job-card').first.tap();dialog=mobile_page.get_by_role('dialog');expect(dialog).to_be_visible()
        assert dialog.evaluate('el=>el.scrollWidth<=el.clientWidth')
        screenshot(mobile_page,'touch-detail-light')
        mobile_page.keyboard.press('Escape');mobile.close()
        check('Fresh touch viewport has usable targets and a contained full-width drawer')
        page.goto(BASE+'/overview');page.get_by_role('button',name='Sign out',exact=True).click()
        page.get_by_role('button',name='Sign in',exact=True).wait_for()
        page.goto(BASE+'/register')
        page.get_by_role('button',name='Create your workspace',exact=True).wait_for()
        page.get_by_label('Email address',exact=True).fill('second-'+secrets.token_hex(6)+'@example.invalid')
        page.get_by_label('Password',exact=False).fill(secrets.token_urlsafe(24))
        page.get_by_role('button',name='Create your workspace',exact=True).click()
        page.get_by_role('heading',name='A clearer next step.',exact=True).wait_for()
        page.get_by_role('link',name='Explore',exact=True).first.click()
        expect(page.locator('.results-bar strong')).to_have_text('0');expect(page.locator('.job-card')).to_have_count(0)
        check('Signing into a second account in the same tab reveals none of the prior account cache')
        assert not errors,errors

    report['javascript_errors']=errors
    browser.close()
 report['passed']=True
except Exception as exc:
 report['passed']=False;report['failure']=str(exc)[:2500]
 raise
finally:
 (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
