"""Self-service MFA and bearer-link recovery; all secrets travel in POST bodies."""
import base64
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field
from sqlalchemy import select

from .account_security import locked_user, revoke_sessions
from .database import get_db
from .founder_security import record, verify_mfa
from .models import AccountMFA, PasswordRecovery, now
from .schemas import StrictModel
from .security import decrypt, digest, encrypt, password_hash, verify_password
from .services import event


class Reauthentication(StrictModel):
    current_password: str = Field(min_length=1, max_length=256)
    otp: str = Field(default="", max_length=8)


class RecoveryInput(StrictModel):
    token: str = Field(min_length=20, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


def create_router(current_user, require_locked_session, throttle):
    router = APIRouter(prefix="/api/auth", tags=["Account security"])

    def authenticate(data, request, user, db):
        throttle(request)
        user = require_locked_session(request, user, db)
        if not verify_password(data.current_password, user.password_hash):
            raise HTTPException(403, "Current password is incorrect")
        return user

    @router.get('/mfa')
    def status(user=Depends(current_user), db=Depends(get_db)):
        row = db.get(AccountMFA, user.id)
        return {"enabled":bool(row and row.enabled)}

    @router.post('/mfa/setup')
    def setup(data:Reauthentication, request:Request, user=Depends(current_user), db=Depends(get_db)):
        user = authenticate(data,request,user,db)
        row = db.get(AccountMFA,user.id)
        if row and row.enabled:
            raise HTTPException(409,"Disable existing MFA before replacing the authenticator")
        secret = base64.b32encode(secrets.token_bytes(20)).decode().rstrip('=')
        if row:
            row.secret_encrypted,row.last_counter = encrypt(secret),-1
            row.created_at=now()
        else:
            db.add(AccountMFA(user_id=user.id,secret_encrypted=encrypt(secret),enabled=False,last_counter=-1))
        record(db,user.id,"mfa_setup",request)
        db.commit()
        label = quote("InternPilot:"+decrypt(user.email_encrypted),safe='')
        return {"secret":secret,"uri":f"otpauth://totp/{label}?secret={secret}&issuer=InternPilot&algorithm=SHA1&digits=6&period=30"}

    @router.post('/mfa/enable')
    def enable(data:Reauthentication, request:Request, user=Depends(current_user), db=Depends(get_db)):
        user = authenticate(data,request,user,db)
        row = db.get(AccountMFA,user.id)
        if not row or row.enabled:
            raise HTTPException(409,"Start a new authenticator setup first")
        if row.created_at < (datetime.now(timezone.utc)-timedelta(minutes=15)).isoformat():
            raise HTTPException(409,"Authenticator setup expired; start again")
        row.enabled=True
        verify_mfa(db,user,data.otp)
        user.security_version += 1
        request.state.session.mfa_verified_at=now()
        revoke_sessions(db,user.id,except_token_hash=request.state.session.token_hash)
        record(db,user.id,"mfa_enabled",request)
        event(db,user.id,"mfa_enabled","Authenticator enabled; other sessions revoked",notify=True)
        db.commit()
        return {"enabled":True}

    @router.post('/mfa/disable')
    def disable(data:Reauthentication, request:Request, user=Depends(current_user), db=Depends(get_db)):
        user = authenticate(data,request,user,db)
        row=db.get(AccountMFA,user.id)
        if not row or not row.enabled:
            raise HTTPException(409,"MFA is not enabled")
        verify_mfa(db,user,data.otp)
        db.delete(row)
        user.security_version += 1
        revoke_sessions(db,user.id,except_token_hash=request.state.session.token_hash)
        record(db,user.id,"mfa_disabled",request)
        event(db,user.id,"mfa_disabled","Authenticator disabled; other sessions revoked",notify=True)
        db.commit()
        return {"enabled":False}

    @router.post('/recover')
    def recover(data:RecoveryInput, request:Request, db=Depends(get_db)):
        throttle(request)
        token_hash=digest(data.token)
        candidate=db.get(PasswordRecovery,token_hash)
        if candidate is None:
            raise HTTPException(403,"Recovery link is invalid or expired")
        user=locked_user(db,user_id=candidate.user_id)
        row=db.scalar(select(PasswordRecovery).where(PasswordRecovery.token_hash==token_hash).with_for_update().execution_options(populate_existing=True))
        if (not user or user.disabled or user.role=="owner" or not row or row.used_at or row.expires_at<=now()
                or row.security_version != user.security_version):
            raise HTTPException(403,"Recovery link is invalid or expired")
        if verify_password(data.new_password,user.password_hash):
            raise HTTPException(422,"Choose a different new password")
        user.password_hash=password_hash(data.new_password)
        user.security_version += 1
        user.reset_required=False
        row.used_at=now()
        revoke_sessions(db,user.id)
        record(db,user.id,"password_recovered",request)
        event(db,user.id,"password_recovered","Recovery completed; sessions revoked and automation remains paused",notify=True)
        db.commit()
        return {"ok":True,"instruction":"Sign in with your new password; MFA is unchanged"}

    return router
