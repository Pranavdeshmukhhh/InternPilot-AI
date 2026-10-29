"""Named owner access to business records, never credential retrieval.

Every sensitive read/action requires a fresh password check, purpose and audit.
There is no anonymous bootstrap, shared master password or arbitrary SQL API.
"""
import mimetypes
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import object_session

from .account_security import locked_user, revoke_sessions
from .config import settings
from .database import get_db
from .models import (User, LoginSession, Source, Opportunity, Application, Document, Task,
                     Notification, NotificationDelivery, SavedOpportunity, AuditEvent, now)
from .schemas import StrictModel, Credentials
from .security import decrypt, decrypt_bytes, encrypt, password_hash, verify_password
from .services import document_view, event, source_view


class OwnerAction(StrictModel):
    current_password: str = Field(min_length=1,max_length=256)
    purpose: str = Field(min_length=8,max_length=300)
    consent: bool
    otp: str = Field(default="",max_length=8)


class WorkerControl(OwnerAction):
    paused: bool
    paused_kinds: list[str] = Field(default_factory=list, max_length=4)


class OwnerStatus(OwnerAction):
    disabled: bool


class OwnerPassword(OwnerAction):
    new_password: str = Field(min_length=12,max_length=256)


class OwnerInvitation(OwnerAction):
    email: str = Field(min_length=5,max_length=254)
    expires_days: int = Field(default=7,ge=1,le=7)

    @field_validator("email")
    @classmethod
    def email_valid(cls, value):
        return Credentials.email_valid(value)


def account_view(row):
    return {key:getattr(row,key) for key in ("id","role","disabled","created_at","last_login_at","last_seen_at")} | {"email":decrypt(row.email_encrypted)}


def create_router(current_user, require_locked_session, throttle):
    router = APIRouter(prefix="/api/owner",tags=["Workspace owner"])

    def owner(request:Request,user=Depends(current_user),db=Depends(get_db)):
        # Shared admission uses a separate short transaction. Run it before the
        # account lock, especially on SQLite (one writer), never inside check().
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            throttle(request)
        user = require_locked_session(request,user,db)
        if user.disabled or user.role!="owner":
            raise HTTPException(403,"Workspace owner access is required")
        return user

    def check(request,actor,data):
        if data.consent is not True or len(data.purpose.strip())<8:
            raise HTTPException(422,"Confirm this specific action and give a meaningful access reason")
        if not verify_password(data.current_password,actor.password_hash):
            raise HTTPException(403,"Owner password is incorrect")
        from .founder_security import sensitive_mfa
        sensitive_mfa(object_session(actor),actor,request.state.session,data.otp)
        secrets = [data.current_password,data.otp,getattr(data,"new_password","")]
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

    @router.get("/invitations")
    def invitations(actor=Depends(owner),db=Depends(get_db)):
        from .invitations import PREFIX, view
        from .models import CoordinationState
        from sqlalchemy import case
        rows = db.scalars(select(CoordinationState).where(CoordinationState.key.startswith(PREFIX),
                          CoordinationState.value["actor_id"].as_string()==actor.id)
                          .order_by(case((((CoordinationState.value["status"].as_string()=="pending") &
                                          (CoordinationState.value["expires_at"].as_string()>now())),0),else_=1),
                                    CoordinationState.value["created_at"].as_string().desc(),CoordinationState.key).limit(100)).all()
        return {"items":[view(row) for row in rows],"limit":100,"invitation_only":settings.invitation_only}

    @router.post("/invitations")
    def invite(data:OwnerInvitation,request:Request,actor=Depends(owner),db=Depends(get_db)):
        check(request,actor,data)
        from .invitations import create, view
        from .security import digest
        if not settings.invitation_only or not settings.allow_registration:
            raise HTTPException(409,"Enable INVITATION_ONLY=true and ALLOW_REGISTRATION=true to issue invitations")
        if db.scalar(select(User.id).where(User.email_hash==digest(data.email))):
            raise HTTPException(409,"This account already exists; manage its access in Accounts")
        row,token = create(db,actor.id,data.email,data.expires_days)
        result = {**view(row),"token":token}
        event(db,actor.id,"owner_invitation_created","Created email-bound invitation "+result["id"])
        db.commit()
        return result

    @router.post("/invitations/{invitation_id}/revoke")
    def revoke_invitation(invitation_id:str,data:OwnerAction,request:Request,actor=Depends(owner),db=Depends(get_db)):
        check(request,actor,data)
        from .invitations import locked
        row = locked(db,invitation_id)
        if row is None:
            raise HTTPException(404,"Invitation not found")
        if row.value["status"] != "pending":
            raise HTTPException(409,"Only an unused invitation can be revoked")
        row.value = {**row.value,"status":"revoked","revoked_at":now()}
        event(db,actor.id,"owner_invitation_revoked","Revoked invitation "+invitation_id)
        db.commit()
        return {"ok":True}

    @router.post("/workers/control")
    def control_workers(data:WorkerControl,request:Request,actor=Depends(owner),db=Depends(get_db)):
        check(request,actor,data)
        if set(data.paused_kinds)-{"discovery","application","outreach","gmail_sync"}:
            raise HTTPException(422,"Unsupported worker role")
        from .coordination import locked_state
        row = locked_state(db,"workers")
        row.value = {"paused":data.paused,"paused_kinds":data.paused_kinds}
        event(db,actor.id,"worker_control",data.purpose.strip())
        db.commit()
        return row.value

    @router.get("/workers/control")
    def worker_control(actor=Depends(owner),db=Depends(get_db)):
        from .models import CoordinationState
        row = db.get(CoordinationState,"workers")
        return row.value if row else {"paused":False,"paused_kinds":[]}

    @router.get("/overview")
    def overview(actor=Depends(owner),db=Depends(get_db)):
        tables = {model.__tablename__:db.scalar(select(func.count()).select_from(model)) for model in
                  (User,Source,Opportunity,Application,Document,Task,Notification,NotificationDelivery,SavedOpportunity,AuditEvent)}
        active = db.scalar(select(func.count()).select_from(LoginSession).where(LoginSession.expires_at>now()))
        return {"tables":tables,"active_sessions":active,"disabled_accounts":db.scalar(select(func.count()).select_from(User).where(User.disabled==True)),
                "credential_access":"Passwords, password hashes, tokens and browser session state are never returned"}

    @router.post("/unlock")
    def unlock_console(data:OwnerAction,request:Request,actor=Depends(owner),db=Depends(get_db)):
        check(request,actor,data)
        from .founder_security import unlock, record
        unlock(db,actor,request.state.session)
        record(db,actor.id,"founder_reauthenticated",request)
        event(db,actor.id,"owner_console_unlocked","Founder console unlocked for five minutes")
        db.commit()
        return {"ok":True,"expires_in":300}

    @router.get("/report")
    def founder_report(request:Request,section:Literal['overview','activity','analytics','security','applications','automation','infrastructure','settings']='overview',actor=Depends(owner),db=Depends(get_db)):
        from .founder_security import require_unlock
        from .founder_reports import report
        require_unlock(db,actor,request.state.session)
        result=report(db,section)
        event(db,actor.id,"owner_report_read","Founder report viewed: "+section)
        db.commit()
        return result

    @router.post("/users/{user_id}/recovery")
    def recover_account(user_id:str,data:OwnerAction,request:Request,actor=Depends(owner),db=Depends(get_db)):
        check(request,actor,data)
        user=target(db,user_id,change=True)
        from .founder_security import recovery, record
        token,expiry=recovery(db,user)
        record(db,user.id,"recovery_issued",request)
        audit(db,actor,user,"recovery_issued",data.purpose)
        db.commit()
        return {"token":token,"expires_at":expiry,"delivery":"Share privately; no email was sent"}

    @router.get("/users")
    def users(search:str=Query("",max_length=254),page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),actor=Depends(owner),db=Depends(get_db)):
        from .security import digest
        base=select(User).order_by(User.created_at,User.id)
        offset=(page-1)*page_size
        limited=False
        if search.strip():
            term = search.strip().casefold()
            if '@' in term and '.' in term.partition('@')[2]:
                base=base.where(User.email_hash==digest(term))
                selected=list(db.scalars(base))
                total=len(selected)
                selected=selected[offset:offset+page_size]
            else:
                candidates=list(db.scalars(base.limit(1001)))
                limited=len(candidates)>1000
                selected=[row for row in candidates[:1000] if term in decrypt(row.email_encrypted).casefold() or term in row.id.casefold()]
                total=len(selected);selected=selected[offset:offset+page_size]
        else:
            total=db.scalar(select(func.count()).select_from(User))
            selected=list(db.scalars(base.offset(offset).limit(page_size)))
        identifiers=[row.id for row in selected]
        counts=dict(db.execute(select(LoginSession.user_id,func.count()).where(LoginSession.user_id.in_(identifiers),LoginSession.expires_at>now()).group_by(LoginSession.user_id)).all()) if identifiers else {}
        rows=[{**account_view(row),"display_name":decrypt(row.profile_encrypted).get("name", ""),
               "active_sessions":counts.get(row.id,0),"reset_required":row.reset_required} for row in selected]
        event(db,actor.id,"owner_directory_read","Viewed registered account directory")
        db.commit()
        return {"items":rows,"total":total,"page":page,"page_size":page_size,"search_limited":limited}

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
        from .models import SecurityEvent
        security_events=[{"kind":row.kind,"at":row.created_at,"address_tag":row.address_tag} for row in db.scalars(select(SecurityEvent).where(SecurityEvent.user_id==user.id).order_by(SecurityEvent.created_at.desc()).limit(100))]
        return {"account":account_view(user),"profile":profile,"applications":applications,"documents":documents,"sources":sources,"security_events":security_events,
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
        user.security_version += 1
        user.reset_required = False
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
