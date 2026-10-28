"""Gmail boundaries are mocked; real encrypted DB transactions and worker gates run."""
import asyncio
import base64
import logging
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import gmail, outreach, services, worker
from app.database import Base
from app.models import GmailConnection, GmailOAuthState, OutreachContact, OutreachMessage, OutreachReply, OutreachSettings, Task, User, now
from app.outreach_schemas import ContactInput, MessageEdit, SenderSettings
from app.schemas import Policy, Profile
from app.security import decrypt, digest, encrypt
from app.security_logs import OAuthAccessFilter
from test_api_worker import stack  # noqa: F401 -- pytest fixture


@pytest.fixture
def mailbox(tmp_path,monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path/'outreach.db'}",connect_args={"check_same_thread":False})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine,expire_on_commit=False)
    for module in (outreach,gmail,services,worker):
        monkeypatch.setattr(module,"SessionLocal",sessions)
    profile = Profile(name="Synthetic Candidate",degree="B.Tech",university="Synthetic University",projects=[{"name":"Queue monitor","description":"Built a Python queue monitor.","skills":["Python"]}],verified_fields=["name","projects","degree","university","country","graduation_year"]).model_dump()
    contact_data = ContactInput(name="Synthetic Recruiter",email="recruiter@example.invalid",company="Synthetic Employer",source_url="https://example.invalid/team",employer_fact="I read your published engineering internship announcement.",verified=True).model_dump()
    policy = SenderSettings(enabled=True,start_hour=0,end_hour=24,weekdays_only=False,gap_minutes=10).model_dump()
    with sessions() as db:
        user = User(email_hash=digest("candidate@example.invalid"),email_encrypted=encrypt("candidate@example.invalid"),password_hash="synthetic-unused",profile_encrypted=encrypt(profile),policy_encrypted=encrypt(Policy().model_dump()))
        db.add(user);db.flush()
        contact = OutreachContact(owner_id=user.id,email_hash=digest(contact_data["email"]),data_encrypted=encrypt(contact_data))
        db.add(contact);db.flush()
        connection = GmailConnection(owner_id=user.id,email_hash=digest("sender@example.invalid"),data_encrypted=encrypt({"email":"sender@example.invalid","access_token":"synthetic-access","refresh_token":"synthetic-refresh","expires_at":time.time()+3600}))
        db.add(connection);db.add(OutreachSettings(owner_id=user.id,data_encrypted=encrypt(policy)));db.commit()
        owner,contact_id = user.id,contact.id
    def message(*,approved=True,**changes):
        with sessions() as db:
            content = outreach.factual_draft(profile,contact_data,policy)
            row = OutreachMessage(owner_id=owner,contact_id=contact_id,content_encrypted=encrypt(content),status="approved" if approved else "draft",scheduled_at=now() if approved else None,approved_at=now() if approved else None,**changes)
            if approved:
                row.approval_digest = outreach.content_digest(content,profile,db.get(GmailConnection,owner))
            db.add(row);db.commit();return row.id
    yield SimpleNamespace(db=sessions,owner=owner,contact=contact_id,profile=profile,contact_data=contact_data,policy=policy,message=message)
    engine.dispose()


def test_factual_drafts_templates_and_tone_cannot_invent_unverified_projects(mailbox):
    result = outreach.factual_draft(mailbox.profile,mailbox.contact_data,mailbox.policy)
    assert "Built a Python queue monitor" in result["body"]
    assert "Synthetic Employer" in result["subject"] and "reply 'stop'" in result["body"]
    with pytest.raises(HTTPException):
        outreach.factual_draft({**mailbox.profile,"verified_fields":["name"]},mailbox.contact_data,mailbox.policy)
    with pytest.raises(HTTPException):
        outreach.factual_draft(mailbox.profile,mailbox.contact_data,{**mailbox.policy,"body_template":"{name.__class__}"})
    formal = outreach.factual_draft(mailbox.profile,mailbox.contact_data,{**mailbox.policy,"tone":"formal","subject_template":"{role}: {name}"})
    assert formal["body"].startswith("Dear Synthetic Recruiter")


@pytest.mark.parametrize("changes",[{"daily_limit":41},{"gap_minutes":0},{"timezone":"invalid/zone"},{"start_hour":19,"end_hour":9}])
def test_invalid_sender_policy_is_rejected(changes):
    with pytest.raises(ValueError):
        SenderSettings(**changes)


def test_email_and_subject_header_injection_rejected():
    with pytest.raises(ValueError):
        ContactInput(name="A",email="a@example.com\nBcc: x@example.com",company="C",source_url="https://example.com",verified=True)
    with pytest.raises(ValueError):
        MessageEdit(subject="Hello\r\nBcc: x@example.com",body="Facts",facts_verified=True)


def test_ist_window_weekends_and_gap_schedule():
    policy = SenderSettings().model_dump()
    # Friday evening in India rolls through the weekend to Monday 09:00 IST.
    at = datetime(2026,10,23,17,0,tzinfo=timezone.utc)
    assert outreach.next_slot(policy,at)==datetime(2026,10,26,3,30,tzinfo=timezone.utc)


def test_only_specific_approved_message_is_sent_once_with_receipt(mailbox,monkeypatch):
    calls = []
    async def request(owner,method,path,**kwargs):
        calls.append((owner,method,path,kwargs))
        return {"id":"synthetic-provider-receipt","threadId":"synthetic-thread"}
    monkeypatch.setattr(gmail,"request",request)
    draft = mailbox.message(approved=False)
    message = mailbox.message()
    asyncio.run(outreach.send_message(draft))
    asyncio.run(outreach.send_message(message))
    asyncio.run(outreach.send_message(message))
    assert len(calls)==1
    decoded = base64.urlsafe_b64decode(calls[0][3]["payload"]["raw"]).decode()
    assert "recruiter@example.invalid" in decoded and "Message-ID:" in decoded
    with mailbox.db() as db:
        row = db.get(OutreachMessage,message)
        assert row.status=="sent" and row.provider_id=="synthetic-provider-receipt"
        assert "delivery is not confirmed" in row.reason
        assert db.get(OutreachMessage,draft).status=="draft"


@pytest.mark.parametrize("restriction",["emergency","disabled","paused","optout","profile","sender","reply"])
def test_all_sending_gates_prevent_network(mailbox,monkeypatch,restriction):
    message = mailbox.message()
    with mailbox.db() as db:
        user = db.get(User,mailbox.owner)
        if restriction=="emergency":user.policy_encrypted=encrypt({**Policy().model_dump(),"emergency_stop":True})
        if restriction=="disabled":user.disabled=True
        if restriction=="paused":db.get(OutreachSettings,mailbox.owner).data_encrypted=encrypt({**mailbox.policy,"enabled":False})
        if restriction=="optout":db.get(OutreachContact,mailbox.contact).status="opted_out"
        if restriction=="profile":user.profile_encrypted=encrypt({**mailbox.profile,"name":"Changed"})
        if restriction=="sender":db.get(GmailConnection,mailbox.owner).data_encrypted=encrypt({"email":"changed@example.invalid"})
        if restriction=="reply":db.add(OutreachReply(owner_id=mailbox.owner,contact_id=mailbox.contact,provider_id="reply-1",kind="reply",data_encrypted=encrypt({})))
        db.commit()
    async def forbidden(*args,**kwargs):pytest.fail("Forbidden outbound request")
    monkeypatch.setattr(gmail,"request",forbidden)
    asyncio.run(outreach.send_message(message))
    with mailbox.db() as db:
        assert db.get(OutreachMessage,message).sending_started_at is None


def test_gap_and_daily_cap_are_enforced_before_checkpoint(mailbox,monkeypatch):
    async def forbidden(*args,**kwargs):pytest.fail("Quota/gap must prevent sending")
    monkeypatch.setattr(gmail,"request",forbidden)
    message = mailbox.message()
    with mailbox.db() as db:
        db.get(GmailConnection,mailbox.owner).last_reserved_at=now()
        db.commit()
    asyncio.run(outreach.send_message(message))
    with mailbox.db() as db:
        row = db.get(OutreachMessage,message)
        assert row.status=="approved" and row.sending_started_at is None
        assert services.timestamp(row.scheduled_at)>datetime.now(timezone.utc)+timedelta(minutes=8)
        db.get(GmailConnection,mailbox.owner).last_reserved_at=None
        db.get(OutreachSettings,mailbox.owner).data_encrypted=encrypt({**mailbox.policy,"daily_limit":1})
        row.scheduled_at=now()
        previous = OutreachMessage(owner_id=mailbox.owner,contact_id=mailbox.contact,content_encrypted=encrypt({}),status="sent",sending_started_at=now())
        db.add(previous);db.commit()
    asyncio.run(outreach.send_message(message))
    with mailbox.db() as db:
        assert db.get(OutreachMessage,message).sending_started_at is None
        assert services.timestamp(db.get(OutreachMessage,message).scheduled_at)>datetime.now(timezone.utc)+timedelta(hours=1)


def test_provider_timeout_and_restart_never_retry_uncertain_send(mailbox,monkeypatch):
    calls = []
    async def timeout(*args,**kwargs):calls.append(1);raise TimeoutError("synthetic secret must not be recorded")
    monkeypatch.setattr(gmail,"request",timeout)
    message = mailbox.message()
    asyncio.run(outreach.send_message(message));asyncio.run(outreach.send_message(message))
    with mailbox.db() as db:
        row=db.get(OutreachMessage,message)
        assert row.status=="uncertain" and row.sending_started_at and "synthetic secret" not in row.reason
        row.status="sending"
        task=Task(owner_id=mailbox.owner,kind="outreach",payload={"message_id":message},dedupe_key="outreach:"+message,status="running",lease_until="2000-01-01T00:00:00+00:00")
        db.add(task);db.commit()
    assert worker.recover_expired()==1
    with mailbox.db() as db:assert db.get(OutreachMessage,message).status=="uncertain"
    assert len(calls)==1


@pytest.mark.parametrize("text,kind",[("Thanks, please apply through the careers page.","reply"),("stop","opt_out"),("Please remove me from this list.","opt_out")])
def test_reply_tracking_stops_followups_and_deduplicates(mailbox,monkeypatch,text,kind):
    sent = mailbox.message()
    with mailbox.db() as db:
        row=db.get(OutreachMessage,sent);row.status,row.provider_id,row.thread_id="sent","outbound-1","thread-1";db.commit()
    pending=mailbox.message(approved=False)
    async def request(*args,**kwargs):
        return {"messages":[{"id":"reply-1","internalDate":"1792728000000","payload":{"mimeType":"text/plain","headers":[{"name":"From","value":"Synthetic Recruiter <recruiter@example.invalid>"},{"name":"Subject","value":"Re: Internship"}],"body":{"data":base64.urlsafe_b64encode(text.encode()).decode()}}}]}
    monkeypatch.setattr(gmail,"request",request)
    asyncio.run(outreach.sync_replies(mailbox.owner));asyncio.run(outreach.sync_replies(mailbox.owner))
    with mailbox.db() as db:
        replies=list(db.scalars(select(OutreachReply)))
        assert len(replies)==1 and replies[0].kind==kind
        assert db.get(OutreachMessage,pending).status=="cancelled"
        if kind=="opt_out":assert db.get(OutreachContact,mailbox.contact).status=="opted_out"


def test_oauth_pkce_single_use_session_binding_and_encrypted_tokens(mailbox,monkeypatch):
    monkeypatch.setenv("GMAIL_CLIENT_ID","synthetic-id")
    monkeypatch.setenv("GMAIL_CLIENT_SECRET","synthetic-client-secret")
    monkeypatch.setenv("GMAIL_REDIRECT_URI","http://localhost:3000/api/outreach/gmail/callback")
    with mailbox.db() as db:
        authorization=gmail.start_authorization(db,mailbox.owner,"synthetic-session")
    params=parse_qs(urlsplit(authorization).query)
    assert params["code_challenge_method"]==["S256"] and "synthetic-client-secret" not in authorization
    state=params["state"][0]
    with mailbox.db() as db:
        with pytest.raises(HTTPException):asyncio.run(gmail.finish_authorization(db,mailbox.owner,"wrong-session",state,"code"))
    def provider(request):
        if request.url.path.endswith("/token"):
            return httpx.Response(200,json={"access_token":"oauth-access","refresh_token":"oauth-refresh","expires_in":3600,"scope":" ".join(gmail.SCOPES)})
        return httpx.Response(200,json={"email":"verified@example.invalid","email_verified":True})
    async def finish():
        async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as client:
            with mailbox.db() as db:return await gmail.finish_authorization(db,mailbox.owner,"synthetic-session",state,"synthetic-code",client=client)
    assert asyncio.run(finish())=="verified@example.invalid"
    with mailbox.db() as db:
        row=db.get(GmailConnection,mailbox.owner)
        assert b"oauth-access" not in row.data_encrypted and decrypt(row.data_encrypted)["refresh_token"]=="oauth-refresh"
        assert db.get(GmailOAuthState,digest(state)) is None
    with mailbox.db() as db:
        with pytest.raises(HTTPException):asyncio.run(gmail.finish_authorization(db,mailbox.owner,"synthetic-session",state,"synthetic-code"))


def test_token_refresh_and_gmail_transport_use_only_google(mailbox,monkeypatch):
    monkeypatch.setenv("GMAIL_CLIENT_ID","synthetic-id");monkeypatch.setenv("GMAIL_CLIENT_SECRET","synthetic-secret")
    monkeypatch.setenv("GMAIL_REDIRECT_URI","http://localhost:3000/api/outreach/gmail/callback")
    with mailbox.db() as db:
        row=db.get(GmailConnection,mailbox.owner);row.data_encrypted=encrypt({**decrypt(row.data_encrypted),"expires_at":0});db.commit()
    requests=[]
    def provider(request):
        requests.append(request)
        return httpx.Response(200,json={"access_token":"refreshed-token","expires_in":3600} if request.url.host=="oauth2.googleapis.com" else {"messages":[]})
    async def call():
        async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as client:return await gmail.request(mailbox.owner,"GET","messages",params={"q":"in:sent"},client=client)
    assert asyncio.run(call())=={"messages":[]}
    assert len(requests)==2 and requests[1].headers["authorization"]=="Bearer refreshed-token"
    assert {request.url.host for request in requests}=={"oauth2.googleapis.com","gmail.googleapis.com"}


def test_oauth_access_logs_redact_code_and_state():
    record=logging.LogRecord("uvicorn.access",20,"test",1,'%s - "%s %s HTTP/%s" %d',('host','GET','/api/outreach/gmail/callback?code=private-code&state=private-state','1.1',303),None)
    assert OAuthAccessFilter().filter(record)
    assert "private-code" not in record.getMessage() and "private-state" not in record.getMessage()


def test_standalone_bounce_requires_exact_original_id_and_recipient(mailbox,monkeypatch):
    sent=mailbox.message()
    with mailbox.db() as db:
        row=db.get(OutreachMessage,sent);row.status="sent";row.sending_started_at=now();rfc=row.rfc_message_id;db.commit()
    pending=mailbox.message(approved=False)
    async def provider(owner,method,path,**kwargs):
        if path=='messages':return {'messages':[{'id':'dsn-1'}],'nextPageToken':'synthetic-page'}
        body='Final-Recipient: rfc822; recruiter@example.invalid\nOriginal-Message-ID: '+rfc+'\nStatus: 5.1.1'
        return {'payload':{'mimeType':'text/plain','headers':[{'name':'From','value':'mailer-daemon@googlemail.com'},{'name':'Subject','value':'Delivery failed'}],'body':{'data':base64.urlsafe_b64encode(body.encode()).decode()}}}
    monkeypatch.setattr(gmail,'request',provider)
    asyncio.run(outreach.sync_bounces(mailbox.owner))
    with mailbox.db() as db:
        assert db.get(OutreachContact,mailbox.contact).status=='bounced'
        assert db.get(OutreachMessage,pending).status=='cancelled'
        assert db.scalar(select(OutreachReply)).kind=='bounce'
        assert decrypt(db.get(GmailConnection,mailbox.owner).data_encrypted)['bounce_page_token']=='synthetic-page'


def test_uncertain_receipt_reconciliation_verifies_headers_not_just_search_hit(mailbox,monkeypatch):
    message=mailbox.message()
    with mailbox.db() as db:
        row=db.get(OutreachMessage,message);row.status='uncertain';row.sending_started_at=now();rfc=row.rfc_message_id;db.commit()
    header_matches=False
    async def provider(owner,method,path,**kwargs):
        if path=='messages':return {'messages':[{'id':'found-1','threadId':'found-thread'}]}
        return {'threadId':'found-thread','labelIds':['SENT'],'internalDate':'1792728000000','payload':{'headers':[{'name':'Message-ID','value':rfc if header_matches else 'wrong-id'},{'name':'To','value':'recruiter@example.invalid'}]}}
    monkeypatch.setattr(gmail,'request',provider)
    assert asyncio.run(outreach.reconcile_message(mailbox.owner,message))['status']=='uncertain'
    header_matches=True
    assert asyncio.run(outreach.reconcile_message(mailbox.owner,message))['status']=='sent'
    with mailbox.db() as db:assert db.get(OutreachMessage,message).sent_at=='2026-10-23T04:00:00+00:00'


def test_contact_draft_api_privacy_and_approval_blockers(stack):  # noqa: F811
    owner,_=stack.register();other,_=stack.register("other@example.invalid")
    contact={"name":"Synthetic Recruiter","email":"recruiter@example.invalid","company":"Synthetic Employer","source_url":"https://example.invalid/team","role":"Software internship","verified":True}
    saved=owner.post('/api/outreach/contacts',json=contact)
    assert saved.status_code==200,saved.text
    contact_id=saved.json()['id']
    assert owner.post('/api/outreach/contacts',json=contact).status_code==409
    assert other.get('/api/outreach').json()['contacts']==[]
    assert other.post('/api/outreach/messages',json={'contact_id':contact_id}).status_code==404
    assert owner.post('/api/outreach/messages',json={'contact_id':contact_id}).status_code==422
    profile=owner.get('/api/profile').json()
    profile.update(name='Synthetic Candidate',projects=[{'name':'Monitor','description':'Built a Python monitor.'}],verified_fields=['name','projects','country','graduation_year'])
    assert owner.put('/api/profile',json=profile).status_code==200
    draft=owner.post('/api/outreach/messages',json={'contact_id':contact_id})
    assert draft.status_code==200,draft.text
    message=draft.json()
    assert message['status']=='draft' and 'Python monitor' in message['body']
    assert owner.post('/api/outreach/messages',json={'contact_id':contact_id}).status_code==409
    assert owner.post('/api/outreach/messages/'+message['id']+'/approve',json={'consent':True,'preview_digest':message['preview_digest']}).status_code==409
    assert other.put('/api/outreach/messages/'+message['id'],json={'subject':'New','body':'Facts','facts_verified':True}).status_code==404
    edited=owner.put('/api/outreach/messages/'+message['id'],json={'subject':'Reviewed facts','body':'Factual message','facts_verified':True})
    assert edited.status_code==200 and edited.json()['status']=='draft'
    user_id=owner.get('/api/auth/session').json()['user']['id']
    stack.python("from app.database import SessionLocal; from app.models import GmailConnection; from app.security import encrypt,digest;\nwith SessionLocal() as db: db.add(GmailConnection(owner_id="+repr(user_id)+",email_hash=digest('synthetic-sender@example.invalid'),data_encrypted=encrypt({'email':'synthetic-sender@example.invalid'}))); db.commit()")
    assert owner.post('/api/outreach/messages/'+message['id']+'/approve',json={'consent':True,'preview_digest':message['preview_digest']}).status_code==409
    approved=owner.post('/api/outreach/messages/'+message['id']+'/approve',json={'consent':True,'preview_digest':edited.json()['preview_digest']})
    assert approved.status_code==200 and approved.json()['status']=='approved'
    assert owner.post('/api/outreach/contacts/'+contact_id+'/opt-out').status_code==200
    assert owner.get('/api/outreach').json()['messages'][0]['status']=='cancelled'
    assert owner.post('/api/outreach/contacts',json=contact).status_code==409
    with stack.db() as db:
        dump='\n'.join(db.iterdump())
        assert 'recruiter@example.invalid' not in dump and 'Factual message' not in dump


def test_unconfigured_oauth_and_policy_limits_are_honest(stack):  # noqa: F811
    client,_=stack.register()
    snapshot=client.get('/api/outreach').json()
    assert snapshot['gmail_configured'] is False and snapshot['connection'] is None
    assert client.post('/api/outreach/gmail/connect',json={'consent':True}).status_code==503
    assert client.put('/api/outreach/settings',json={'daily_limit':41}).status_code==422
    assert client.put('/api/outreach/settings',json={'timezone':'invalid/zone'}).status_code==422
    assert client.put('/api/outreach/settings',json={'enabled':True}).status_code==409
    assert client.get('/api/operations').json()['recent_scans']==[]


@pytest.mark.parametrize('stack',[{'GMAIL_CLIENT_ID':'synthetic-id','GMAIL_CLIENT_SECRET':'synthetic-secret','GMAIL_REDIRECT_URI':'http://localhost:3000/api/outreach/gmail/callback'}],indirect=True)
def test_disconnect_invalidates_pending_oauth_and_retains_mutation_csrf(stack):  # noqa: F811
    client,_=stack.register()
    connected=client.post('/api/outreach/gmail/connect',json={'consent':True})
    assert connected.status_code==200,connected.text
    assert 'samesite=lax' in connected.headers['set-cookie'].lower()
    state=parse_qs(urlsplit(connected.json()['authorization_url']).query)['state'][0]
    assert client.request('DELETE','/api/outreach/gmail',json={'consent':True}).status_code==200
    # A later completion from the abandoned Google tab cannot reconnect.
    assert client.get('/api/outreach/gmail/callback',params={'state':state,'error':'access_denied'}).status_code==400
