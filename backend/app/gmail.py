"""Pinned Google OAuth/Gmail transport. Tokens never leave server-side storage."""
import base64
import hashlib
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlsplit

import httpx
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from .account_security import locked_user
from .config import settings
from .database import SessionLocal
from .models import GmailConnection, GmailOAuthState, now
from .security import decrypt, digest, encrypt
from .models import User

SCOPES = ("openid","email","https://www.googleapis.com/auth/gmail.send","https://www.googleapis.com/auth/gmail.readonly")


def configuration():
    client_id,secret,redirect = (os.getenv(key,"") for key in ("GMAIL_CLIENT_ID","GMAIL_CLIENT_SECRET","GMAIL_REDIRECT_URI"))
    if not all((client_id,secret,redirect)):
        raise HTTPException(503,"Configure GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET and GMAIL_REDIRECT_URI on the server")
    parts = urlsplit(redirect)
    origin = f"{parts.scheme}://{parts.netloc}"
    local = not settings.production and parts.hostname in {"localhost","127.0.0.1"} and parts.scheme=="http"
    if (parts.scheme!="https" and not local) or origin not in {*settings.cors_origins,settings.public_origin} or parts.path!="/api/outreach/gmail/callback" or parts.query or parts.fragment or parts.username:
        raise HTTPException(503,"Gmail redirect must use the application's exact trusted origin and /api/outreach/gmail/callback")
    return client_id,secret,redirect


def configured():
    try:
        configuration()
        return True
    except HTTPException:
        return False


def start_authorization(db,user_id,session_token):
    client_id,_,redirect = configuration()
    token,verifier = secrets.token_urlsafe(32),secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    db.execute(delete(GmailOAuthState).where(GmailOAuthState.expires_at<now()))
    db.execute(delete(GmailOAuthState).where(GmailOAuthState.owner_id==user_id))
    db.add(GmailOAuthState(state_hash=digest(token),owner_id=user_id,session_hash=digest(session_token),verifier_encrypted=encrypt(verifier),expires_at=(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat()))
    db.commit()
    return "https://accounts.google.com/o/oauth2/v2/auth?"+urlencode({"client_id":client_id,"redirect_uri":redirect,"response_type":"code","scope":" ".join(SCOPES),"state":token,"code_challenge":challenge,"code_challenge_method":"S256","access_type":"offline","prompt":"consent","include_granted_scopes":"true"})


async def _json(client,method,url,**kwargs):
    try:
        response = await client.request(method,url,follow_redirects=False,**kwargs)
    except httpx.HTTPError:
        raise HTTPException(503,"Google did not confirm this request; inspect the recorded action before retrying") from None
    if response.status_code==429:
        raise HTTPException(429,"Google quota reached; sending is paused until a later check")
    if response.status_code in {401,403}:
        raise HTTPException(409,"Gmail authorization or provider policy needs attention")
    if response.is_error or response.is_redirect:
        raise HTTPException(502,"Google rejected the request; no successful action is claimed")
    try:
        result = response.json()
        if not isinstance(result,dict):
            raise ValueError
        return result
    except ValueError:
        raise HTTPException(502,"Google returned an unsupported response") from None


async def finish_authorization(db,user_id,session_token,state,code,client=None):
    client_id,secret,redirect = configuration()
    row = db.scalar(select(GmailOAuthState).where(GmailOAuthState.state_hash==digest(state)).with_for_update())
    if not row or row.owner_id!=user_id or row.session_hash!=digest(session_token) or row.expires_at<=now():
        raise HTTPException(400,"OAuth state is invalid, expired, already used or belongs to another session")
    verifier = decrypt(row.verifier_encrypted)
    db.delete(row);db.commit()  # Single use, including provider failures.
    if client is None:
        async with httpx.AsyncClient(timeout=20,trust_env=True) as transport:
            return await _finish(db,user_id,code,client_id,secret,redirect,verifier,transport)
    return await _finish(db,user_id,code,client_id,secret,redirect,verifier,client)


async def _finish(db,user_id,code,client_id,secret,redirect,verifier,client):
    tokens = await _json(client,"POST","https://oauth2.googleapis.com/token",data={"client_id":client_id,"client_secret":secret,"redirect_uri":redirect,"code":code,"code_verifier":verifier,"grant_type":"authorization_code"})
    if not {SCOPES[2],SCOPES[3]}.issubset(set(str(tokens.get("scope","")).split())) or not tokens.get("access_token") or not tokens.get("refresh_token"):
        raise HTTPException(409,"Offline Gmail send and read permissions are required; reconnect and approve the requested scopes")
    identity = await _json(client,"GET","https://www.googleapis.com/oauth2/v3/userinfo",headers={"Authorization":"Bearer "+tokens["access_token"]})
    email = str(identity.get("email") or "").strip().casefold()
    if identity.get("email_verified") is not True or "@" not in email or any(c in email for c in "\r\n"):
        raise HTTPException(409,"Google did not return a verified sender identity")
    locked_user(db,user_id=user_id)
    other = db.scalar(select(GmailConnection).where(GmailConnection.email_hash==digest(email),GmailConnection.owner_id!=user_id))
    if other:
        raise HTTPException(409,"This Gmail sender is already linked to another workspace account")
    row = db.get(GmailConnection,user_id)
    data = {"email":email,"access_token":tokens["access_token"],"refresh_token":tokens["refresh_token"],"expires_at":time.time()+min(int(tokens.get("expires_in",3600)),3600),"scopes":str(tokens["scope"]).split()}
    if row:
        row.data_encrypted,row.email_hash,row.status = encrypt(data),digest(email),"connected"
    else:
        db.add(GmailConnection(owner_id=user_id,email_hash=digest(email),data_encrypted=encrypt(data)))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409,"This Gmail sender is already linked to another workspace account") from None
    return email


async def access_token(user_id,client):
    with SessionLocal() as db:
        user = locked_user(db,user_id=user_id)
        if not user or user.disabled:
            raise HTTPException(409,"This account is unavailable")
        row = db.get(GmailConnection,user_id)
        if not row or row.status!="connected":
            raise HTTPException(409,"Connect Gmail before sending or syncing")
        data = decrypt(row.data_encrypted)
        if data.get("expires_at",0)<time.time()+60:
            client_id,secret,_ = configuration()
            try:
                response = await _json(client,"POST","https://oauth2.googleapis.com/token",data={"client_id":client_id,"client_secret":secret,"refresh_token":data["refresh_token"],"grant_type":"refresh_token"})
            except HTTPException as exc:
                if exc.status_code==409:
                    row.status="reauthorize"
                    db.commit()
                raise
            if not response.get("access_token"):
                raise HTTPException(409,"Gmail needs authorization again")
            data["access_token"],data["expires_at"] = response["access_token"],time.time()+min(int(response.get("expires_in",3600)),3600)
            row.data_encrypted = encrypt(data)
            db.commit()
        return data["access_token"]


async def request(user_id,method,path,*,payload=None,params=None,client=None):
    if client is None:
        async with httpx.AsyncClient(timeout=25,trust_env=True) as transport:
            return await request(user_id,method,path,payload=payload,params=params,client=transport)
    token = await access_token(user_id,client)
    if method=="POST" and path=="messages/send":
        with SessionLocal() as db:
            user=db.get(User,user_id)
            if not user or user.disabled or decrypt(user.policy_encrypted).get("emergency_stop"):
                raise HTTPException(409,"Sending was stopped before the Gmail request")
    if not path.startswith(("messages","threads")) or ".." in path or "?" in path:
        raise ValueError("Unsupported Gmail path")
    return await _json(client,method,"https://gmail.googleapis.com/gmail/v1/users/me/"+path,headers={"Authorization":"Bearer "+token},json=payload,params=params)
