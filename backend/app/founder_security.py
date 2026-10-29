"""Account security primitives. Never serialize credentials or raw event inputs."""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select

from .models import AccountMFA, CoordinationState, PasswordRecovery, SecurityEvent, now
from .security import decrypt, digest, encrypt, _load_key


def record(db, user_id, kind, request=None):
    address = request.client.host if request is not None and request.client else ""
    key = hashlib.sha256(_load_key() + b"security-event-address").digest()
    tag = hmac.new(key, address.encode(), hashlib.sha256).hexdigest()[:24] if address else ""
    db.add(SecurityEvent(user_id=user_id, kind=kind, address_tag=tag))


def totp(secret, counter):
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    raw = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = raw[-1] & 15
    return str((struct.unpack(">I", raw[offset:offset+4])[0] & 0x7fffffff) % 1000000).zfill(6)


def verify_mfa(db, user, code):
    row = db.get(AccountMFA, user.id)
    if not row or not row.enabled:
        return False
    counter = int(time.time()) // 30
    if not code.isascii() or not code.isdigit() or len(code) != 6:
        raise HTTPException(403, "A fresh authenticator code is required")
    secret = decrypt(row.secret_encrypted)
    for value in (counter, counter-1, counter+1):
        if value > row.last_counter and hmac.compare_digest(totp(secret, value), code):
            row.last_counter = value
            return True
    raise HTTPException(403, "Authenticator code is invalid or already used")


def sensitive_mfa(db, user, session, code=""):
    row = db.get(AccountMFA, user.id)
    if not row or not row.enabled:
        return
    fresh = (datetime.now(timezone.utc)-timedelta(minutes=5)).isoformat()
    if session.mfa_verified_at and session.mfa_verified_at >= fresh:
        return
    verify_mfa(db, user, code)
    session.mfa_verified_at = now()


def unlock(db, user, session):
    from .coordination import locked_state
    row = locked_state(db, "founder-unlock:" + session.token_hash)
    row.value = {"user_id":user.id, "version":user.security_version,
                 "until":(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()}


def require_unlock(db, user, session):
    row = db.get(CoordinationState, "founder-unlock:" + session.token_hash)
    if not row or row.value.get("user_id") != user.id or row.value.get("version") != user.security_version or row.value.get("until", "") <= now():
        raise HTTPException(403, "Reauthenticate to unlock the founder console for five minutes")


def recovery(db, user):
    from .account_security import revoke_sessions
    user.security_version += 1
    user.reset_required = True
    revoke_sessions(db, user.id)
    token = secrets.token_urlsafe(40)
    row = PasswordRecovery(token_hash=digest(token), user_id=user.id, security_version=user.security_version,
                           expires_at=(datetime.now(timezone.utc)+timedelta(minutes=30)).isoformat())
    db.add(row)
    policy = decrypt(user.policy_encrypted)
    policy["emergency_stop"] = True
    user.policy_encrypted = encrypt(policy)
    return token, row.expires_at


def founder_exists(db, *, except_id=None):
    from .models import User
    statement = select(User.id).where(User.role == "owner")
    if except_id:
        statement = statement.where(User.id != except_id)
    return db.scalar(statement.limit(1)) is not None
