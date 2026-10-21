"""Named owner access to business records, never credential retrieval.

Every sensitive read/action requires a fresh password check, purpose and audit.
There is no anonymous bootstrap, shared master password or arbitrary SQL API.
"""
import mimetypes
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import Field
from sqlalchemy import func, select

from .account_security import locked_user, revoke_sessions
from .database import get_db
from .models import (User, LoginSession, Source, Opportunity, Application, Document, Task,
                     Notification, NotificationDelivery, SavedOpportunity, AuditEvent, now)
from .schemas import StrictModel
from .security import decrypt, decrypt_bytes, encrypt, password_hash, verify_password
from .services import document_view, event, source_view


class OwnerAction(StrictModel):
    current_password: str = Field(min_length=1,max_length=256)
    purpose: str = Field(min_length=8,max_length=300)
    consent: bool


class OwnerStatus(OwnerAction):
    disabled: bool


class OwnerPassword(OwnerAction):
    new_password: str = Field(min_length=12,max_length=256)


def account_view(row):
    return {key:getattr(row,key) for key in ("id","role","disabled","created_at","last_login_at","last_seen_at")} | {"email":decrypt(row.email_encrypted)}


def create_router(current_user, require_locked_session, throttle):
    router = APIRouter(prefix="/api/owner",tags=["Workspace owner"])

    def owner(request:Request,user=Depends(current_user),db=Depends(get_db)):
        user = require_locked_session(request,user,db)
        if user.disabled or user.role!="owner":
            raise HTTPException(403,"Workspace owner access is required")
        return user

    def check(request,actor,data):
        throttle(request)
        if data.consent is not True or len(data.purpose.strip())<8:
            raise HTTPException(422,"Confirm this specific action and give a meaningful access reason")
        if not verify_password(data.current_password,actor.password_hash):
            raise HTTPException(403,"Owner password is incorrect")
        secrets = [data.current_password,getattr(data,"new_password","")]
        if any(secret and secret in data.purpose for secret in secrets):
            raise HTTPException(422,"Do not include passwords in the recorded access reason")

    def target(db,user_id,*,change=False):
        user = db.get(User,user_id)
        if user is None:
            raise HTTPException(404,"Account not found")
        if change and user.role=="owner":
            raise HTTPException(409,"Owner account security is managed through Account security or the local operator CLI")
        return locked_user(db,user_id=user_id) if change else user

    def audit(db,actor,subject,kind,purpose):
        event(db,actor.id,"owner_"+kind,f"Account {subject.id}: {purpose.strip()}")
        if subject.id!=actor.id:
            event(db,subject.id,"owner_account_access","Workspace owner action recorded: "+kind.replace("_"," "),notify=True)

    @router.get("/overview")
    def overview(actor=Depends(owner),db=Depends(get_db)):
        tables = {model.__tablename__:db.scalar(select(func.count()).select_from(model)) for model in
                  (User,Source,Opportunity,Application,Document,Task,Notification,NotificationDelivery,SavedOpportunity,AuditEvent)}
        active = db.scalar(select(func.count()).select_from(LoginSession).where(LoginSession.expires_at>now()))
        return {"tables":tables,"active_sessions":active,"disabled_accounts":db.scalar(select(func.count()).select_from(User).where(User.disabled==True)),
                "credential_access":"Passwords, password hashes, tokens and browser session state are never returned"}

    @router.get("/users")
    def users(search:str=Query("",max_length=254),page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),actor=Depends(owner),db=Depends(get_db)):
        rows = [account_view(row) for row in db.scalars(select(User).order_by(User.created_at,User.id))]
        if search.strip():
            term = search.strip().casefold()
            rows = [row for row in rows if term in row["email"].casefold() or term in row["id"].casefold()]
        offset = (page-1)*page_size
        event(db,actor.id,"owner_directory_read","Viewed registered account directory")
        db.commit()
        return {"items":rows[offset:offset+page_size],"total":len(rows),"page":page,"page_size":page_size}

    @router.post("/users/{user_id}/inspect")
    def inspect_user(user_id:str,data:OwnerAction,request:Request,actor=Depends(owner),db=Depends(get_db)):
        check(request,actor,data)
        user = target(db,user_id)
        profile = decrypt(user.profile_encrypted)
        profile.pop("verified_answers",None)
        applications = [{key:getattr(row,key) for key in ("id","opportunity_id","status","reason","confirmation_id","created_at","updated_at")} for row in
                        db.scalars(select(Application).where(Application.owner_id==user.id).order_by(Application.created_at.desc()).limit(200))]
        documents = [document_view(row) for row in db.scalars(select(Document).where(Document.owner_id==user.id).order_by(Document.created_at.desc()).limit(200))]
        sources = [source_view(row) for row in db.scalars(select(Source).where(Source.owner_id==user.id))]
        audit(db,actor,user,"records_inspected",data.purpose)
        db.commit()
        return {"account":account_view(user),"profile":profile,"applications":applications,"documents":documents,"sources":sources,
                "limits":{"applications":200,"documents":200},"excluded":"Credentials, browser state and private custom-answer vault"}

    @router.post("/users/{user_id}/documents/{doc_id}/download")
    def download(user_id:str,doc_id:str,data:OwnerAction,request:Request,actor=Depends(owner),db=Depends(get_db)):
        check(request,actor,data)
        user = target(db,user_id)
        row = db.get(Document,doc_id)
        if row is None or row.owner_id!=user.id:
            raise HTTPException(404,"Document not found")
        content = decrypt_bytes(row.content_encrypted)
        audit(db,actor,user,"document_downloaded",data.purpose)
        db.commit()
        return Response(content,media_type="image/png" if row.kind=="screenshot" else mimetypes.guess_type(row.filename)[0] or "application/octet-stream",
                        headers={"Content-Disposition":f"attachment; filename*=UTF-8''{quote(row.filename,safe='')}"})

    @router.post("/users/{user_id}/status")
    def status(user_id:str,data:OwnerStatus,request:Request,actor=Depends(owner),db=Depends(get_db)):
        check(request,actor,data)
        user = target(db,user_id,change=True)
        user.disabled = data.disabled
        revoked = 0
        if data.disabled:
            revoked = revoke_sessions(db,user.id)
            policy = decrypt(user.policy_encrypted)
            policy["emergency_stop"] = True
            user.policy_encrypted = encrypt(policy)
        audit(db,actor,user,"account_disabled" if data.disabled else "account_enabled",data.purpose)
        db.commit()
        return {"account":account_view(user),"revoked_sessions":revoked,"automation_resumed":False}

    @router.post("/users/{user_id}/sessions/revoke")
    def sessions(user_id:str,data:OwnerAction,request:Request,actor=Depends(owner),db=Depends(get_db)):
        check(request,actor,data)
        user = target(db,user_id,change=True)
        count = revoke_sessions(db,user.id)
        audit(db,actor,user,"sessions_revoked",data.purpose)
        db.commit()
        return {"revoked_sessions":count}

    @router.post("/users/{user_id}/password")
    def reset_password(user_id:str,data:OwnerPassword,request:Request,actor=Depends(owner),db=Depends(get_db)):
        check(request,actor,data)
        user = target(db,user_id,change=True)
        user.password_hash = password_hash(data.new_password)
        revoke_sessions(db,user.id)
        policy = decrypt(user.policy_encrypted)
        policy["emergency_stop"] = True
        user.policy_encrypted = encrypt(policy)
        audit(db,actor,user,"password_reset",data.purpose)
        db.commit()
        return {"ok":True,"sessions_revoked":True,"emergency_stop":True,"instruction":"Share the replacement password privately; ask the account holder to change it"}

    @router.get("/audit")
    def audit_log(actor=Depends(owner),db=Depends(get_db)):
        return [{key:getattr(row,key) for key in ("id","owner_id","kind","message","created_at")} for row in
                db.scalars(select(AuditEvent).where(AuditEvent.kind.like("owner_%")).order_by(AuditEvent.created_at.desc()).limit(200))]

    return router
