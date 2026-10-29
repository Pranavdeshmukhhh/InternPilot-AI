"""Email-bound, one-use invitations in the existing durable coordination store.

The owner gets the bearer secret once. Only its digest and encrypted email are
stored. Consumption and account creation share the caller's transaction.
"""
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, update

from .models import CoordinationState, now
from .security import decrypt, digest, encrypt

PREFIX = "account-invite:"


def view(row):
    value = row.value
    status = value["status"]
    if status == "pending" and value["expires_at"] <= now():
        status = "expired"
    return {"id": row.key[len(PREFIX):], "email": decrypt(value["email_encrypted"]),
            "status": status, "created_at": value["created_at"], "expires_at": value["expires_at"]}


def create(db, actor_id, email, days):
    # Owner route serializes creation on the actor's existing account lock.
    pending = db.scalars(select(CoordinationState).where(
        CoordinationState.key.startswith(PREFIX),
        CoordinationState.value["actor_id"].as_string() == actor_id,
        CoordinationState.value["status"].as_string() == "pending",
        CoordinationState.value["expires_at"].as_string() > now(),
    ).limit(101)).all()
    if len(pending) >= 100:
        raise HTTPException(409, "Revoke an unused invitation before creating another (100 pending maximum)")
    identifier = uuid4().hex
    token = identifier + "." + secrets.token_urlsafe(32)
    stamp = now()
    row = CoordinationState(key=PREFIX + identifier, value={
        "token_digest": digest(token), "email_hash": digest(email),
        "email_encrypted": encrypt(email).decode("ascii"), "actor_id": actor_id,
        "created_at": stamp, "expires_at": (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(),
        "status": "pending",
    })
    db.add(row)
    db.flush()
    return row, token


def locked(db, identifier):
    if not re.fullmatch(r"[a-f0-9]{32}", identifier):
        return None
    key = PREFIX + identifier
    # UPDATE serializes SQLite as well as PostgreSQL without creating rows for
    # invalid codes. PostgreSQL also retains the row lock through registration.
    db.execute(update(CoordinationState).where(CoordinationState.key == key).values(key=key))
    return db.scalar(select(CoordinationState).where(CoordinationState.key == key)
                     .with_for_update().execution_options(populate_existing=True))


def consume(db, email, token):
    identifier = token.partition(".")[0]
    row = locked(db, identifier)
    if (not row or row.value.get("status") != "pending" or row.value["expires_at"] <= now()
            or not hmac.compare_digest(row.value["token_digest"], digest(token))
            or not hmac.compare_digest(row.value["email_hash"], digest(email))):
        raise HTTPException(403, "A valid invitation for this email address is required")
    row.value = {**row.value, "status": "used", "used_at": now()}
    return row
