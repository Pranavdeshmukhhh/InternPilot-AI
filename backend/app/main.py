import asyncio
import hmac
import mimetypes
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePath
from statistics import mean
from urllib.parse import quote, urlsplit
from typing import Literal
from fastapi import Depends, FastAPI, HTTPException, Request, Response, UploadFile, File, Query
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select, func, text, or_, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .config import settings
from .database import get_db, SessionLocal
from .migrate import migrate
from .models import User, LoginSession, Source, Opportunity, Application, Document, Task, Notification, AuditEvent, SavedOpportunity, NotificationSettings, NotificationDelivery, now
from .schemas import Credentials, RegistrationCredentials, PasswordChange, Profile, Policy, SourceInput, ApplyInput, GenerateInput, ConsentInput, StopInput, StatusInput, ReadInput
from .security import encrypt, decrypt, decrypt_bytes, digest, password_hash, verify_password, approval_digest
from .account_security import locked_user, revoke_sessions
from .services import event, visible_jobs, job_for_user, job_view, source_view, application_view, document_view, enqueue, store_document, seed_demo, application_priority
from .body_limit import BodyLimitMiddleware
from .owner_console import create_router as create_owner_router
from .outreach_api import create_router as create_outreach_router
from .operations_api import create_router as create_operations_router
from .discovery_filters import DiscoveryCriteria
from .opportunity_query import query_opportunities
from . import security_logs  # noqa: F401 -- installs OAuth access-log redaction.


@asynccontextmanager
async def lifespan(app):
    migrate()
    yield


app = FastAPI(title="InternPilot AI",version="1.0.0",lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=settings.cors_origins,allow_credentials=True,allow_methods=["GET","POST","PUT","PATCH","DELETE"],allow_headers=["Content-Type","X-CSRF-Token"])
app.add_middleware(BodyLimitMiddleware)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # Pydantic's default error includes the original user input; omit it.
    errors = [".".join(map(str,e["loc"]))+": "+e["msg"] for e in exc.errors()]
    return JSONResponse(status_code=422,content={"detail":"; ".join(errors)[:1800]})


@app.middleware("http")
async def security_headers(request, call_next):
    if request.method in {"POST","PUT","PATCH","DELETE"} and request.url.path.startswith("/api/"):
        origin = request.headers.get("origin")
        host_origin = f"{request.url.scheme}://{request.headers.get('host','')}"
        allowed = origin in {*settings.cors_origins, settings.public_origin} or (not settings.production and origin == host_origin)
        if origin and not allowed:
            return JSONResponse(status_code=403,content={"detail":"Request origin is not allowed"})
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Cache-Control"] = "no-store"
    if settings.production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response


def current_user(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("internpilot_session", "")
    session = db.get(LoginSession,digest(token)) if token else None
    if not session or session.expires_at <= now():
        raise HTTPException(401,"Sign in to continue")
    if request.method not in {"GET","HEAD","OPTIONS"}:
        csrf = request.headers.get("x-csrf-token", "")
        if not hmac.compare_digest(csrf.encode("utf-8"),session.csrf_token.encode("utf-8")):
            raise HTTPException(403,"CSRF token is missing or invalid")
    user = db.get(User,session.user_id)
    if not user or user.disabled:
        raise HTTPException(401,"Account no longer exists")
    if not user.last_seen_at or user.last_seen_at < (datetime.now(timezone.utc)-timedelta(minutes=5)).isoformat():
        user.last_seen_at = now()
    request.state.session = session
    # Authentication is its own short unit of work. expire_on_commit=False
    # retains these read facts without pinning a pool connection while the
    # endpoint waits for a thread, generates documents or performs network I/O.
    # Sensitive mutations still re-lock/revalidate through require_locked_session.
    db.commit()
    return user


def issue_session(db, user, response):
    token, csrf = secrets.token_urlsafe(40), secrets.token_urlsafe(32)
    db.add(LoginSession(token_hash=digest(token),user_id=user.id,csrf_token=csrf,expires_at=(datetime.now(timezone.utc)+timedelta(days=7)).isoformat()))
    # Lax permits Google's top-level OAuth return; mutating API calls still
    # require a session-bound CSRF token and exact origin validation.
    response.set_cookie("internpilot_session",token,httponly=True,secure=settings.cookie_secure,samesite="lax",max_age=604800,path="/")
    return {"user":{"id":user.id,"email":decrypt(user.email_encrypted),"role":user.role},"csrf_token":csrf}


def throttle(request):
    from .auth_limits import admit
    address = request.client.host if request.client else "local"
    admit(address)


# Unknown-account verification must not perform an extra scrypt on every request.
_DUMMY_PASSWORD_HASH = password_hash("constant-dummy-password")


@app.get("/api/health")
def health(db: Session=Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status":"ok","test_mode":settings.test_mode,"version":"1.0.0","external_submission_adapters":[],"queue":"durable-database","llm_configured":__import__('os').getenv("LLM_PROVIDER","disabled")!="disabled","allow_registration":settings.allow_registration,"registration_requires_invite":settings.invitation_only or bool(settings.registration_token),"invitation_only":settings.invitation_only}


@app.get("/api/ready")
def readiness(db: Session=Depends(get_db)):
    db.execute(text("SELECT 1"))
    if settings.worker_heartbeat_file:
        try:
            age = time.time() - Path(settings.worker_heartbeat_file).stat().st_mtime
        except OSError:
            age = 999
        if age < 0 or age > 60:
            raise HTTPException(503,"Background worker is not ready")
    return {"status":"ready"}


@app.post("/api/auth/register")
def register(data:RegistrationCredentials,request:Request,response:Response,db:Session=Depends(get_db)):
    if not settings.allow_registration:
        raise HTTPException(403,"Account registration is disabled")
    throttle(request)
    if settings.invitation_only:
        from .invitations import consume
        consume(db, data.email, data.registration_token)
    elif settings.registration_token and not hmac.compare_digest(digest(data.registration_token),digest(settings.registration_token)):
        raise HTTPException(403,"A valid invitation code is required")
    profile = Profile().model_dump()
    # Account email is authenticated for sign-in, but not silently treated as a
    # verified application contact field; onboarding explicitly verifies it.
    profile["email"] = data.email
    user = User(email_hash=digest(data.email),email_encrypted=encrypt(data.email),password_hash=password_hash(data.password),profile_encrypted=encrypt(profile),policy_encrypted=encrypt(Policy().model_dump()))
    user.last_login_at,user.last_seen_at = now(),now()
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409,"This account already exists") from None
    from .discovery import default_sources
    for source in default_sources():
        db.add(Source(owner_id=user.id,**source))
    result = issue_session(db,user,response)
    event(db,user.id,"account_created","Account created; Discovery mode enabled")
    db.commit()
    return result


@app.post("/api/auth/login")
def login(data:Credentials,request:Request,response:Response,db:Session=Depends(get_db)):
    throttle(request)
    user = locked_user(db,email_hash=digest(data.email))
    if not verify_password(data.password,user.password_hash if user else _DUMMY_PASSWORD_HASH) or user is None:
        raise HTTPException(401,"Invalid email or password")
    if user.disabled:
        raise HTTPException(403,"This account is disabled; contact the workspace owner")
    user.last_login_at,user.last_seen_at = now(),now()
    result = issue_session(db,user,response)
    event(db,user.id,"sign_in","Signed in")
    db.commit()
    return result


@app.get("/api/auth/session")
def session(request:Request,user:User=Depends(current_user)):
    return {"user":{"id":user.id,"email":decrypt(user.email_encrypted),"role":user.role},"csrf_token":request.state.session.csrf_token}


@app.post("/api/auth/logout")
def logout(request:Request,response:Response,user:User=Depends(current_user),db:Session=Depends(get_db)):
    db.delete(request.state.session)
    db.commit()
    response.delete_cookie("internpilot_session",path="/")
    return {"ok":True}


def require_locked_session(request, user, db):
    user = locked_user(db,user_id=user.id)
    # Authentication can precede waiting for the account lock. Recheck that
    # this session survived any password change or recovery while waiting.
    active = db.scalar(select(LoginSession).where(LoginSession.token_hash==request.state.session.token_hash,LoginSession.user_id==user.id,LoginSession.expires_at>now())) if user else None
    if not active:
        raise HTTPException(401,"Sign in to continue")
    return user


@app.get("/api/auth/sessions")
def account_sessions(request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
    active = db.scalar(select(func.count()).select_from(LoginSession).where(LoginSession.user_id==user.id,LoginSession.expires_at>now()))
    return {"active_sessions":active,"other_sessions":max(0,active-1),"current_session_expires_at":request.state.session.expires_at}


@app.post("/api/auth/password")
def change_password(data:PasswordChange,request:Request,response:Response,user:User=Depends(current_user),db:Session=Depends(get_db)):
    throttle(request)
    user = require_locked_session(request,user,db)
    if not verify_password(data.current_password,user.password_hash):
        raise HTTPException(403,"Current password is incorrect")
    if hmac.compare_digest(data.current_password.encode(),data.new_password.encode()):
        raise HTTPException(422,"Choose a different new password")
    user.password_hash = password_hash(data.new_password)
    revoke_sessions(db,user.id)
    result = issue_session(db,user,response)
    event(db,user.id,"password_changed","Password changed; all previous sessions signed out",notify=True)
    db.commit()
    return result


@app.post("/api/auth/logout-others")
def logout_other_sessions(request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
    user = require_locked_session(request,user,db)
    revoked = revoke_sessions(db,user.id,except_token_hash=request.state.session.token_hash)
    event(db,user.id,"sessions_revoked","Other account sessions signed out",notify=True)
    db.commit()
    return {"ok":True,"revoked_sessions":revoked,"active_sessions":1}


@app.get("/api/profile")
def get_profile(user:User=Depends(current_user)):
    return Profile.model_validate(decrypt(user.profile_encrypted)).model_dump()


@app.put("/api/profile")
def put_profile(data:Profile,user:User=Depends(current_user),db:Session=Depends(get_db)):
    if len(data.model_dump_json()) > 150000:
        raise HTTPException(413,"Profile exceeds size limit")
    user.profile_encrypted = encrypt(data.model_dump())
    event(db,user.id,"profile_updated","Candidate profile updated; facts marked verified by candidate")
    db.commit()
    return data.model_dump()


@app.get("/api/policy")
def get_policy(user:User=Depends(current_user)):
    return Policy.model_validate(decrypt(user.policy_encrypted)).model_dump()


@app.put("/api/policy")
def put_policy(data:Policy,user:User=Depends(current_user),db:Session=Depends(get_db)):
    # Lock the same user row used by the final-click budget check.
    db.refresh(user,with_for_update=True)
    user.policy_encrypted = encrypt(data.model_dump())
    event(db,user.id,"policy_updated",f"Policy saved: {data.mode}; explicit Auto Apply consent: {data.auto_consent}",notify=True)
    db.commit()
    return data.model_dump()


@app.post("/api/emergency-stop")
def emergency_stop(data:StopInput,user:User=Depends(current_user),db:Session=Depends(get_db)):
    db.refresh(user,with_for_update=True)
    policy = decrypt(user.policy_encrypted)
    policy["emergency_stop"] = data.stopped
    user.policy_encrypted = encrypt(policy)
    event(db,user.id,"emergency_stop","Emergency stop activated" if data.stopped else "Emergency stop cleared",notify=True)
    db.commit()
    return policy


def opportunity_rows(db, user, *, search="", eligibility="", remote="", sort="score", company="", paid="", deadline_before="", kind="", location="", region="all", saved=False, recommended=False, include_closed=False, min_score=0, criteria=None):
    return query_opportunities(db,user,view=job_view,search=search,eligibility=eligibility,remote=remote,sort=sort,company=company,paid=paid,deadline_before=deadline_before,kind=kind,location=location,region=region,saved=saved,recommended=recommended,include_closed=include_closed,min_score=min_score,criteria=criteria)


@app.get("/api/v2/opportunities")
def opportunity_cursor(cursor:str=Query("",max_length=4096),page_size:int=Query(20,ge=1,le=50),
        sort:Literal["newest","deadline"]="newest",kind:Literal["","internship","hackathon","program"]="",
        company:str=Query("",max_length=250),search:str=Query("",max_length=500),location:str=Query("",max_length=250),
        remote:bool=False,saved:bool=False,include_closed:bool=False,search_mode:Literal["substring","text"]="substring",
        user:User=Depends(current_user),db:Session=Depends(get_db)):
    from .catalog_query import cursor_page
    return cursor_page(db,user,cursor=cursor,page_size=page_size,sort=sort,kind=kind,company=company,search=search,
        location=location,remote=remote,saved=saved,include_closed=include_closed,search_mode=search_mode)


@app.get("/api/opportunities")
def opportunities(search:str="",eligibility:str="",remote:str="",sort:Literal["score","newest","deadline"]="score",company:str="",paid:str="",deadline_before:str="",kind:Literal["","internship","hackathon"]="",location:str="",region:Literal["all","local","india","international","worldwide","unknown"]="all",saved:bool=False,recommended:bool=False,include_closed:bool=False,min_score:int=Query(0,ge=0,le=100),criteria:DiscoveryCriteria=Depends(),user:User=Depends(current_user),db:Session=Depends(get_db)):
    return opportunity_rows(db,user,search=search,eligibility=eligibility,remote=remote,sort=sort,company=company,paid=paid,deadline_before=deadline_before,kind=kind,location=location,region=region,saved=saved,recommended=recommended,include_closed=include_closed,min_score=min_score,criteria=criteria)


@app.get("/api/opportunities/page")
def opportunity_page(search:str="",eligibility:str="",remote:str="",sort:Literal["score","newest","deadline"]="score",company:str="",paid:str="",deadline_before:str="",kind:Literal["","internship","hackathon"]="",location:str="",region:Literal["all","local","india","international","worldwide","unknown"]="all",saved:bool=False,recommended:bool=False,include_closed:bool=False,min_score:int=Query(0,ge=0,le=100),page:int=Query(1,ge=1,le=100000),page_size:int=Query(20,ge=1,le=100),criteria:DiscoveryCriteria=Depends(),user:User=Depends(current_user),db:Session=Depends(get_db)):
    return query_opportunities(db,user,page=page,page_size=page_size,view=job_view,search=search,eligibility=eligibility,remote=remote,sort=sort,company=company,paid=paid,deadline_before=deadline_before,kind=kind,location=location,region=region,saved=saved,recommended=recommended,include_closed=include_closed,min_score=min_score,criteria=criteria)


@app.get("/api/saved")
def saved_opportunities(user:User=Depends(current_user),db:Session=Depends(get_db)):
    return opportunity_rows(db,user,saved=True,include_closed=True)


@app.post("/api/imports/opportunities")
async def import_opportunity_export(provider:Literal["jobspy","internscan"]=Query(...),file:UploadFile=File(...),user:User=Depends(current_user),db:Session=Depends(get_db)):
    from .aggregation import records_from_bytes,normalize_record,MAX_IMPORT_BYTES
    from .services import canonical_fingerprint
    content = await file.read(MAX_IMPORT_BYTES+1)
    try:
        records = records_from_bytes(content,file.filename or "export.json")
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from None
    source_kind = "jobspy_feed" if provider=="jobspy" else "internscan"
    source = db.scalar(select(Source).where(Source.owner_id==user.id,Source.kind==source_kind,Source.slug=="uploaded-export"))
    if source is None:
        source = Source(owner_id=user.id,kind=source_kind,slug="uploaded-export",company="JobSpy export" if provider=="jobspy" else "InternScan export",enabled=False,permitted=True,interval_seconds=1800)
        db.add(source);db.flush()
    skipped=0
    ids = set((source.cache or {}).get("active_opportunity_ids",[]))
    normalized = []
    for record in records:
        data = normalize_record(record,source_kind)
        if data is None:
            skipped+=1;continue
        normalized.append(data)
    fingerprints = {digest(user.id + ":" + canonical_fingerprint(data)) for data in normalized}
    existing = set(db.scalars(select(Opportunity.fingerprint).where(Opportunity.fingerprint.in_(fingerprints))))
    from .catalog import ingest
    jobs, _, _, _ = ingest(db, user.id, source, normalized)
    added = len(fingerprints - existing)
    updated = len(normalized) - added
    ids.update(job.id for job in jobs)
    source.cache = {"active_opportunity_ids":sorted(ids),"truncated":True,"uploaded":True}
    source.status,source.last_success,source.discovered_count = "imported",now(),added+updated
    event(db,user.id,"export_imported",f"{provider}: {added} new references, {updated} duplicates updated, {skipped} unsupported records skipped")
    db.commit()
    return {"added":added,"updated":updated,"skipped":skipped,"source_id":source.id,"verification":"Imported references require official employer verification"}


@app.post("/api/saved/{job_id}")
def save_opportunity(job_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    job = job_for_user(db,user.id,job_id)
    if not job:
        raise HTTPException(404,"Opportunity not found")
    locked_user(db, user_id=user.id)
    target = job.canonical_id or job.id
    family = select(Opportunity.id).where(or_(Opportunity.id == target, Opportunity.canonical_id == target))
    if db.scalar(select(SavedOpportunity.opportunity_id).where(SavedOpportunity.owner_id == user.id, SavedOpportunity.opportunity_id.in_(family))) is None:
        try:
            with db.begin_nested():
                db.add(SavedOpportunity(owner_id=user.id,opportunity_id=job_id)); db.flush()
        except IntegrityError:
            pass
        event(db,user.id,"opportunity_saved","Opportunity saved for follow-up")
    db.commit()
    return {"saved":True,"opportunity_id":job_id}


@app.delete("/api/saved/{job_id}")
def unsave_opportunity(job_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    job = job_for_user(db, user.id, job_id)
    if job:
        target = job.canonical_id or job.id
        family = select(Opportunity.id).where(or_(Opportunity.id == target, Opportunity.canonical_id == target))
        db.execute(delete(SavedOpportunity).where(SavedOpportunity.owner_id == user.id, SavedOpportunity.opportunity_id.in_(family)))
        db.commit()
    return {"saved":False,"opportunity_id":job_id}


@app.get("/api/opportunities/{job_id}")
def get_opportunity(job_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    job = job_for_user(db,user.id,job_id)
    if not job:
        raise HTTPException(404,"Opportunity not found")
    return job_view(job,decrypt(user.profile_encrypted))


@app.get("/api/sources")
def sources(user:User=Depends(current_user),db:Session=Depends(get_db)):
    return [source_view(s) for s in db.scalars(select(Source).where(Source.owner_id==user.id))]


@app.get("/api/discovery/regions")
def regional_discovery(user:User=Depends(current_user),db:Session=Depends(get_db)):
    from .geography import local_cities, NEARBY, normalized
    from .regional_search import configured, search_sources
    profile = decrypt(user.profile_encrypted)
    owned = list(db.scalars(select(Source).where(Source.owner_id==user.id)))
    return {"local_cities":local_cities(profile),"nearby_places":{city:list(NEARBY.get(normalized(city),(city,))) for city in local_cities(profile)},
            "include_nearby":profile.get("include_nearby_locations",True),"search_configured":configured(),
            "search_presets":[{**preset,"installed":any(s.kind=="search" and s.slug==preset["slug"] for s in owned)} for preset in search_sources(profile)],
            "source_count":sum(s.enabled and s.permitted for s in owned),
            "note":"Regions use listing location metadata. International and remote listings do not by themselves establish eligibility for Indian students."}


@app.post("/api/discovery/regions/enable")
def enable_regional_discovery(request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
    from .regional_search import configured, search_sources
    if not configured():
        raise HTTPException(409,"Set BRAVE_SEARCH_API_KEY on the server to enable regional web search. Existing ATS, MLH and India feed discovery remains available.")
    user = require_locked_session(request,user,db)
    existing = set(db.scalars(select(Source.slug).where(Source.owner_id==user.id,Source.kind=="search")))
    presets = [preset for preset in search_sources(decrypt(user.profile_encrypted)) if preset["slug"] not in existing]
    if (db.scalar(select(func.count()).select_from(Source).where(Source.owner_id==user.id)) or 0) + len(presets) > 2000:
        raise HTTPException(409,"Source quota reached (2,000 per account)")
    added = 0
    for preset in presets:
        if preset["slug"] in existing:
            continue
        db.add(Source(owner_id=user.id,**preset))
        added += 1
    event(db,user.id,"regional_search_enabled",f"Added {added} regional internship and hackathon search sources")
    db.commit()
    return {"added":added,"note":"Scheduled read-only searches run with the worker; provider usage limits apply. Existing source settings were preserved."}


@app.post("/api/sources")
async def create_source(data:SourceInput,request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
    user=require_locked_session(request,user,db)
    if db.scalar(select(func.count()).select_from(Source).where(Source.owner_id==user.id))>=2000:
        raise HTTPException(409,"Source quota reached (2,000 per account)")
    if data.url:
        from .discovery import validate_public_url
        try:
            await validate_public_url(data.url)
        except ValueError as exc:
            raise HTTPException(422,str(exc)) from None
    row = Source(owner_id=user.id,**data.model_dump())
    db.add(row)
    db.flush()
    event(db,user.id,"source_created",f"Discovery source added: {data.company}")
    db.commit()
    return source_view(row)


@app.patch("/api/sources/{source_id}")
async def update_source(source_id:str,data:dict,user:User=Depends(current_user),db:Session=Depends(get_db)):
    row = db.get(Source,source_id)
    if not row or row.owner_id!=user.id:
        raise HTTPException(404,"Source not found")
    merged = {k:getattr(row,k) for k in SourceInput.model_fields}
    merged.update(data)
    try:
        validated = SourceInput.model_validate(merged)
    except ValueError:
        raise HTTPException(422,"Invalid source fields") from None
    if validated.url:
        from .discovery import validate_public_url
        try:
            await validate_public_url(validated.url)
        except ValueError as exc:
            raise HTTPException(422,str(exc)) from None
    for key,value in validated.model_dump().items():
        setattr(row,key,value)
    row.scan_generation = Source.scan_generation + 1
    row.cache, row.next_run = {}, None
    event(db,user.id,"source_updated",f"Discovery source updated: {row.company}")
    db.commit()
    return source_view(row)


@app.delete("/api/sources/{source_id}")
def delete_source(source_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    row = db.get(Source,source_id)
    if not row or row.owner_id!=user.id:
        raise HTTPException(404,"Source not found")
    from .models import SourceOpportunity
    db.execute(delete(SourceOpportunity).where(SourceOpportunity.source_id == source_id))
    db.delete(row)
    event(db,user.id,"source_deleted","Discovery source removed")
    db.commit()
    return {"ok":True}


def task_view(task):
    return {key:getattr(task,key) for key in ("id","kind","status","attempts","error","created_at","updated_at","lease_until")}


@app.post("/api/discovery/run")
def discovery_run(user:User=Depends(current_user),db:Session=Depends(get_db)):
    if decrypt(user.policy_encrypted)["emergency_stop"]:
        raise HTTPException(409,"Clear the emergency stop before starting discovery")
    enabled = list(db.scalars(select(Source.id).where(Source.owner_id==user.id,Source.enabled==True,Source.permitted==True)))
    if not enabled:
        raise HTTPException(409,"Enable a permitted source before starting discovery")
    queued = [enqueue(db,user.id,"discovery",{"source_id":source_id},f"source:{source_id}") for source_id in enabled]
    event(db,user.id,"discovery_queued","Manual source refresh queued")
    db.commit()
    return {**task_view(queued[0]),"queued_sources":len(queued)}


@app.get("/api/applications")
def applications(user:User=Depends(current_user),db:Session=Depends(get_db)):
    rows = db.execute(select(Application, Opportunity).outerjoin(Opportunity, Opportunity.id == Application.opportunity_id)
        .where(Application.owner_id == user.id).order_by(Application.created_at.desc())).all()
    return [application_view(db, row, job=job) for row, job in rows]


@app.post("/api/applications")
def create_application(data:ApplyInput,request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
    user = require_locked_session(request,user,db)
    policy,profile = decrypt(user.policy_encrypted),decrypt(user.profile_encrypted)
    if policy["emergency_stop"] or policy["mode"]=="discovery":
        raise HTTPException(409,"Enable Assisted Apply and clear emergency stop to prepare applications")
    job = job_for_user(db,user.id,data.opportunity_id)
    if not job:
        raise HTTPException(404,"Opportunity not found")
    view = job_view(job,profile)
    if view["eligibility"]=="ineligible":
        raise HTTPException(422,"Opportunity is ineligible: "+"; ".join(view["reasons"])[:700])
    identity = or_(Opportunity.id == job.id, Opportunity.canonical_id == (job.canonical_id or job.id),
        Opportunity.url_key == job.url_key if job.url_key else False)
    if db.scalar(select(Application).join(Opportunity, Opportunity.id == Application.opportunity_id)
        .where(Application.owner_id==user.id, identity)):
        raise HTTPException(409,"An application already exists for this opportunity")
    row = Application(owner_id=user.id,opportunity_id=job.id)
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409,"An application already exists for this opportunity") from None
    enqueue(db,user.id,"application",{"application_id":row.id},f"application:{row.id}",application_priority(view))
    event(db,user.id,"application_queued","Application preparation queued",row.id)
    db.commit()
    return application_view(db,row)


def owned_application(db,user_id,app_id):
    row = db.get(Application,app_id)
    if not row or row.owner_id!=user_id:
        raise HTTPException(404,"Application not found")
    return row


@app.get("/api/applications/{app_id}/checklist")
def application_checklist(app_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    row = owned_application(db,user.id,app_id)
    job = db.get(Opportunity,row.opportunity_id)
    profile = decrypt(user.profile_encrypted)
    view = job_view(job,profile)
    snapshot = decrypt(row.snapshot_encrypted) if row.snapshot_encrypted else {}
    missing = [field for field in ("name","email","degree","university","skills") if not profile.get(field) or field not in profile.get("verified_fields",[])]
    unresolved = [field.get("label","Question") for field in snapshot.get("form_fields",[]) if field.get("status") in {"unmapped","human_required"}]
    confirmed = bool(row.confirmation_id and row.confirmation_encrypted)
    stages = [
        {"id":"profile","label":"Verified candidate facts","state":"ready" if not missing else "needs_input","detail":"Verified profile facts are available." if not missing else "Verify: "+", ".join(missing)},
        {"id":"eligibility","label":"Eligibility and availability","state":"ready" if view["eligibility"]=="eligible" and view["status"]=="open" else "blocked" if view["eligibility"]=="ineligible" else "needs_input","detail":" ".join(view.get("reasons",[])[:3])},
        {"id":"resume","label":"Factual resume draft","state":"ready" if row.document_id else "waiting","detail":"A versioned PDF is available for your review." if row.document_id else "Generate a draft from verified facts."},
        {"id":"upload","label":"Specific upload approval","state":"uncertain" if row.status=="uncertain" and row.upload_started_at else "started" if row.upload_started_at else "approved" if row.upload_approved_at else "waiting","detail":"An approved file assignment was started; review its recorded outcome." if row.upload_started_at else "Approval applies only to this document, candidate snapshot and application URL."},
        {"id":"questions","label":"Application questions","state":"needs_input" if unresolved else "not_inspected" if not snapshot.get("form_fields") else "ready","detail":"Review: "+", ".join(unresolved[:10]) if unresolved else "Questions are mapped after approved form preparation; unsupported or sensitive questions pause."},
        {"id":"confirmation","label":"Submission confirmation","state":"confirmed" if confirmed else "waiting","detail":"Authoritative confirmation is recorded." if confirmed else "External final submission is completed manually; preparation is not a submission."},
    ]
    return {"application_id":row.id,"stages":stages,"missing_profile_fields":missing,"unresolved_questions":unresolved,"recommended_action":view["recommended_action"],"external_submission_supported":False,"confirmation_id":row.confirmation_id}


@app.post("/api/applications/{app_id}/approve")
def approve_application(app_id:str,data:ConsentInput,user:User=Depends(current_user),db:Session=Depends(get_db)):
    row = owned_application(db,user.id,app_id)
    if not data.consent:
        raise HTTPException(422,"Explicit submission consent is required")
    if not (row.is_demo and settings.test_mode):
        raise HTTPException(409,"No certified submission adapter for this employer. Complete the application on the official site.")
    if row.status!="awaiting_review" or row.submission_started_at:
        raise HTTPException(409,"This application cannot be approved in its current state")
    if decrypt(user.policy_encrypted)["emergency_stop"]:
        raise HTTPException(409,"Emergency stop is active")
    job = db.get(Opportunity,row.opportunity_id)
    from .services import demo_profile
    profile = demo_profile(user.id) if row.is_demo else decrypt(user.profile_encrypted)
    row.approved_at, row.approval_digest, row.status = now(), approval_digest(profile,job.data,row.document_id), "approved"
    enqueue(db,user.id,"application",{"application_id":row.id},f"application:{row.id}")
    event(db,user.id,"approval","Explicit final submission approved",row.id)
    db.commit()
    return application_view(db,row)


@app.post("/api/applications/{app_id}/approve-upload")
def approve_resume_upload(app_id:str,data:ConsentInput,request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
    user = require_locked_session(request,user,db)
    row = owned_application(db,user.id,app_id)
    if not data.consent:
        raise HTTPException(422,"Approval for this specific resume upload is required")
    if row.is_demo or row.status not in {"awaiting_review","needs_input"} or row.upload_started_at or row.submission_started_at:
        raise HTTPException(409,"This upload is not available for approval; reconcile any previous action first")
    job = db.get(Opportunity,row.opportunity_id)
    document = db.get(Document,row.document_id) if row.document_id else None
    profile,policy = decrypt(user.profile_encrypted),decrypt(user.policy_encrypted)
    if policy.get("emergency_stop") or policy.get("mode")=="discovery":
        raise HTTPException(409,"Enable Assisted Apply and clear emergency stop first")
    snapshot = decrypt(row.snapshot_encrypted) if row.snapshot_encrypted else {}
    if not document or document.owner_id!=user.id or snapshot.get("profile")!=profile or snapshot.get("job")!=job.data:
        raise HTTPException(409,"Candidate facts, listing or document changed; prepare and review a fresh draft")
    if job_view(job,profile)["eligibility"]=="ineligible":
        raise HTTPException(409,"This opportunity is no longer eligible")
    if urlsplit(job.data.get("url", "")).scheme!="https":
        raise HTTPException(422,"External application preparation requires an HTTPS application URL")
    row.upload_approved_at,row.upload_approval_digest,row.status = now(),approval_digest(profile,job.data,row.document_id),"queued"
    row.reason = "Specific resume upload approved; final submission remains manual"
    enqueue(db,user.id,"application",{"application_id":row.id,"automatic_preparation":False},f"application:{row.id}",application_priority(job_view(job,profile)))
    event(db,user.id,"upload_approved","Candidate approved this resume and application URL for one assisted upload",row.id)
    db.commit()
    return application_view(db,row)


@app.post("/api/applications/{app_id}/retry")
def retry_application(app_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    row = owned_application(db,user.id,app_id)
    if row.status not in {"failed","needs_input","awaiting_review"} or row.submission_started_at or row.upload_started_at:
        raise HTTPException(409,"Only safely unsubmitted applications can be prepared again")
    policy = decrypt(user.policy_encrypted)
    if policy["emergency_stop"] or policy["mode"]=="discovery":
        raise HTTPException(409,"Enable Assisted Apply and clear emergency stop first")
    row.status,row.reason,row.document_id,row.approved_at,row.approval_digest = "queued","Preparation queued after candidate intervention",None,None,None
    row.upload_approved_at,row.upload_approval_digest = None,None
    enqueue(db,user.id,"application",{"application_id":row.id},f"application:{row.id}")
    event(db,user.id,"retry","Safe pre-submission preparation retry queued",row.id)
    db.commit()
    return application_view(db,row)


@app.patch("/api/applications/{app_id}")
def update_application(app_id:str,data:StatusInput,user:User=Depends(current_user),db:Session=Depends(get_db)):
    row = owned_application(db,user.id,app_id)
    if row.status in {"queued","preparing","approved","submitting"}:
        raise HTTPException(409,"Wait for the worker to finish before changing status")
    row.status,row.reason,row.updated_at = data.status,"Status reported manually by candidate",now()
    event(db,user.id,"manual_status",f"Candidate reported application status: {data.status}",row.id)
    db.commit()
    return application_view(db,row)


@app.get("/api/documents")
def documents(user:User=Depends(current_user),db:Session=Depends(get_db)):
    return [document_view(r) for r in db.scalars(select(Document).where(Document.owner_id==user.id).order_by(Document.created_at.desc()))]


@app.post("/api/documents/upload")
async def upload_document(file:UploadFile=File(...),user:User=Depends(current_user),db:Session=Depends(get_db)):
    from .document_processing import parse_resume_isolated, ParserBusyError
    content = await file.read(8*1024*1024+1)
    filename = PurePath((file.filename or "resume.pdf").replace("\\","/")).name[:180]
    try:
        parsed = await parse_resume_isolated(content,filename)
    except ParserBusyError as exc:
        raise HTTPException(503, str(exc), headers={"Retry-After": "5"}) from None
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from None
    row = store_document(db,user.id,{"content":content,"filename":filename,**parsed},"original")
    event(db,user.id,"resume_imported","Original resume encrypted; extracted suggestions require verification")
    db.commit()
    return {**document_view(row),**parsed}


@app.post("/api/documents/generate")
def generate_document(data:GenerateInput,user:User=Depends(current_user),db:Session=Depends(get_db)):
    from .documents import generate_resume,generate_cover_letter
    job = job_for_user(db,user.id,data.opportunity_id)
    if not job:
        raise HTTPException(404,"Opportunity not found")
    try:
        output = (generate_resume if data.kind=="resume" else generate_cover_letter)(decrypt(user.profile_encrypted),job.data)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from None
    row = store_document(db,user.id,output,data.kind,job.id)
    event(db,user.id,"document_generated",f"Verified-facts {data.kind} generated; version {row.version}")
    db.commit()
    return document_view(row)


@app.get("/api/documents/{doc_id}/download")
def download_document(doc_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    row = db.get(Document,doc_id)
    if not row or row.owner_id!=user.id:
        raise HTTPException(404,"Document not found")
    content = decrypt_bytes(row.content_encrypted)
    media = "image/png" if row.kind=="screenshot" else mimetypes.guess_type(row.filename)[0] or "application/octet-stream"
    return Response(content,media_type=media,headers={"Content-Disposition":f"attachment; filename*=UTF-8''{quote(row.filename,safe='')}"})


@app.get("/api/events")
def events(user:User=Depends(current_user),db:Session=Depends(get_db)):
    return [{key:getattr(r,key) for key in ("id","kind","message","application_id","created_at")} for r in db.scalars(select(AuditEvent).where(AuditEvent.owner_id==user.id).order_by(AuditEvent.created_at.desc()).limit(250))]


@app.get("/api/notifications")
def notifications(user:User=Depends(current_user),db:Session=Depends(get_db)):
    return [{key:getattr(r,key) for key in ("id","kind","message","read","created_at","opportunity_id")} for r in db.scalars(select(Notification).where(Notification.owner_id==user.id).order_by(Notification.created_at.desc()).limit(150))]


@app.get("/api/notification-settings")
def notification_settings(user:User=Depends(current_user),db:Session=Depends(get_db)):
    from .notification_delivery import validate_notification_settings, delivery_config_status
    row = db.get(NotificationSettings,user.id)
    values = validate_notification_settings(decrypt(row.settings_encrypted) if row else {})
    return {**values,"delivery_config":delivery_config_status()}


@app.put("/api/notification-settings")
def update_notification_settings(data:dict,user:User=Depends(current_user),db:Session=Depends(get_db)):
    from .notification_delivery import validate_notification_settings, materialize_delivery_drafts, delivery_config_status
    if len(str(data))>12000:
        raise HTTPException(413,"Notification preferences exceed size limit")
    values = validate_notification_settings(data)
    row = db.get(NotificationSettings,user.id)
    if row is None:
        row = NotificationSettings(owner_id=user.id,settings_encrypted=encrypt(values))
        db.add(row)
    else:
        row.settings_encrypted,row.updated_at = encrypt(values),now()
    event(db,user.id,"notification_preferences","Notification preferences updated; outgoing messages require individual approval")
    db.commit()
    materialize_delivery_drafts(db,user.id)
    db.commit()
    return {**values,"delivery_config":delivery_config_status()}


@app.get("/api/notification-deliveries")
def notification_deliveries(user:User=Depends(current_user),db:Session=Depends(get_db)):
    from .notification_delivery import materialize_delivery_drafts, delivery_view
    materialize_delivery_drafts(db,user.id)
    db.commit()
    rows = db.scalars(select(NotificationDelivery).where(NotificationDelivery.owner_id==user.id).order_by(NotificationDelivery.created_at.desc()).limit(150))
    return [delivery_view(row) for row in rows]


@app.post("/api/notification-deliveries/{delivery_id}/send")
def approve_notification_delivery(delivery_id:str,data:ConsentInput,user:User=Depends(current_user),db:Session=Depends(get_db)):
    from .notification_delivery import send_delivery
    return send_delivery(db,user.id,delivery_id,consent=data.consent)


@app.patch("/api/notifications/{notification_id}")
def read_notification(notification_id:str,data:ReadInput,user:User=Depends(current_user),db:Session=Depends(get_db)):
    row = db.get(Notification,notification_id)
    if not row or row.owner_id!=user.id:
        raise HTTPException(404,"Notification not found")
    row.read = data.read
    db.commit()
    return {"ok":True}


@app.get("/api/events/stream")
async def stream_events(request:Request):
    # Authenticate in a short unit of work, not a yield dependency that retains
    # a checked-out connection for the entire 55-second stream.
    def authenticate():
        with SessionLocal() as auth_db:
            return current_user(request, auth_db)
    user = await asyncio.to_thread(authenticate)
    def latest_event():
        with SessionLocal() as db:
            return db.scalar(select(func.max(AuditEvent.created_at)).where(AuditEvent.owner_id==user.id))
    async def updates():
        cursor = now()
        started = time.monotonic()
        client,pubsub = None,None
        if settings.redis_url:
            try:
                import redis.asyncio as redis
                client = redis.from_url(settings.redis_url,socket_connect_timeout=0.5,socket_timeout=1)
                pubsub = client.pubsub()
                await pubsub.subscribe(f"internpilot:{user.id}")
            except Exception:
                if client:
                    await client.aclose()
                client,pubsub = None,None
        try:
            yield "event: ready\ndata: {}\n\n"
            while time.monotonic()-started<55:
                if await request.is_disconnected():
                    break
                wakeup = None
                if pubsub:
                    try:
                        wakeup = await pubsub.get_message(ignore_subscribe_messages=True,timeout=1)
                    except Exception:
                        await pubsub.aclose()
                        pubsub = None
                latest = await asyncio.to_thread(latest_event)
                if wakeup or (latest and latest>cursor):
                    cursor = latest or cursor
                    yield "data: {\"event\":\"refresh\"}\n\n"
                else:
                    yield ": heartbeat\n\n"
                await asyncio.sleep(1 if pubsub else 2)
        finally:
            if pubsub:
                await pubsub.aclose()
            if client:
                await client.aclose()
    return StreamingResponse(updates(),media_type="text/event-stream",headers={"X-Accel-Buffering":"no"})


@app.get("/api/tasks")
def tasks(user:User=Depends(current_user),db:Session=Depends(get_db)):
    return [task_view(r) for r in db.scalars(select(Task).where(Task.owner_id==user.id).order_by(Task.created_at.desc()).limit(150))]


@app.get("/api/dashboard")
def dashboard(user:User=Depends(current_user),db:Session=Depends(get_db)):
    profile = decrypt(user.profile_encrypted)
    jobs = visible_jobs(db,user.id)
    real_jobs = [j for j in jobs if not j.data.get("is_demo")]
    views = [job_view(j,profile) for j in real_jobs]
    rows = list(db.scalars(select(Application).where(Application.owner_id==user.id,Application.is_demo==False)))
    measured = [r for r in rows if r.submission_started_at]
    def avg(values):
        clean = [v for v in values if v is not None]
        return round(mean(clean),2) if clean else None
    submitted = sum(bool(r.confirmation_id) for r in rows)
    metrics = {"opportunities":len(real_jobs),"eligible":sum(v["eligibility"]=="eligible" for v in views),"review":sum(v["eligibility"]=="review" for v in views),"applications":len(rows),"submitted":submitted,"needs_input":sum(r.status in {"needs_input","uncertain","awaiting_review"} for r in rows),"success_rate":round(100*submitted/len(measured),1) if measured else None,"discovery_latency_seconds":avg(j.discovery_latency_seconds for j in real_jobs),"preparation_seconds":avg(r.preparation_seconds for r in rows),"submission_seconds":avg(r.submission_seconds for r in rows)}
    metrics.update({"internships":sum(v["opportunity_type"]=="internship" and v["status"] not in {"closed","expired"} for v in views),"hackathons":sum(v["opportunity_type"]=="hackathon" and v["status"] not in {"closed","expired"} for v in views),"open":sum(v["status"]=="open" for v in views),"unverified":sum(v["status"]=="unverified" for v in views),"saved":db.scalar(select(func.count()).select_from(SavedOpportunity).where(SavedOpportunity.owner_id==user.id)),"approaching_deadlines":sum(v.get("deadline_urgency") in {"within_24h","within_3d"} and v["status"] not in {"closed","expired"} for v in views)})
    from .monitoring import worker_status
    return {"metrics":metrics,"recent_events":events(user,db)[:10],"source_health":sources(user,db),"worker":worker_status(db,user.id)}


@app.post("/api/demo/seed")
def demo_seed(user:User=Depends(current_user),db:Session=Depends(get_db)):
    if not settings.test_mode:
        raise HTTPException(404,"Test mode is disabled")
    row = seed_demo(db,user.id)
    event(db,user.id,"local_demo","Isolated LOCAL TEST opportunity added; candidate profile unchanged")
    db.commit()
    return job_view(row,decrypt(user.profile_encrypted))


@app.post("/api/demo/run")
def demo_run(user:User=Depends(current_user),db:Session=Depends(get_db)):
    if not settings.test_mode:
        raise HTTPException(404,"Test mode is disabled")
    if decrypt(user.policy_encrypted)["emergency_stop"]:
        raise HTTPException(409,"Emergency stop is active")
    job = seed_demo(db,user.id)
    row = db.scalar(select(Application).where(Application.owner_id==user.id,Application.opportunity_id==job.id))
    if row:
        return {"application":application_view(db,row),"duplicate_prevented":True}
    row = Application(owner_id=user.id,opportunity_id=job.id,is_demo=True)
    db.add(row)
    db.flush()
    task = enqueue(db,user.id,"application",{"application_id":row.id},f"application:{row.id}",100)
    event(db,user.id,"local_demo","Authorized local browser demo queued using a synthetic test candidate",row.id)
    db.commit()
    return {"application":application_view(db,row),"task":task_view(task),"duplicate_prevented":False}


if settings.test_mode:
    from .test_portal import router as test_router
    app.include_router(test_router)


app.include_router(create_owner_router(current_user,require_locked_session,throttle))
app.include_router(create_outreach_router(current_user,require_locked_session))
app.include_router(create_operations_router(current_user,require_locked_session))


from .coordination import QueueCapacityError


@app.exception_handler(QueueCapacityError)
async def queue_overload(request: Request, exc: QueueCapacityError):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=503, content={"detail":str(exc)}, headers={"Retry-After":"30"})


@app.post("/api/tasks/{task_id}/requeue")
def requeue_task(task_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    task = db.scalar(select(Task).where(Task.id == task_id, Task.owner_id == user.id).with_for_update())
    if not task:
        raise HTTPException(404, "Task not found")
    if task.kind not in {"discovery", "gmail_sync"} or task.status != "failed":
        raise HTTPException(409, "Use reviewed workflows for external actions")
    if decrypt(user.policy_encrypted).get("emergency_stop"):
        raise HTTPException(409, "Clear emergency stop first")
    enqueue(db, user.id, task.kind, task.payload, task.dedupe_key, task.priority)
    event(db, user.id, "task_requeued", "Explicitly requeued a failed read-only task")
    db.commit()
    return task_view(task)


@app.get("/api/sources/{source_id}/diagnostics")
def source_diagnostics(source_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    source = db.get(Source, source_id)
    if not source or source.owner_id != user.id:
        raise HTTPException(404, "Source not found")
    from .catalog import reviewed_source
    from .models import DiscoveryHealth
    registry = reviewed_source(db, source)
    health = db.get(DiscoveryHealth, registry.id if registry else source.id)
    return {"source":source_view(source), "shared":bool(registry),
            "next_attempt":health.next_attempt if health else source.next_run,
            "consecutive_failures":health.failures if health else source.failures,
            "last_error_class":health.last_error if health else None,
            "checkpoint":{k:v for k,v in (health.checkpoint if health else {}).items() if k in {"offset", "updated_at"}}}
