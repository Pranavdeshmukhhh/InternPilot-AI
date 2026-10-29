"""Shared, bounded sign-in admission using the existing durable state table.

Counts are fixed five-minute windows, not a credential lockout. A global budget
bounds work and row cardinality even when clients rotate addresses. PostgreSQL
row locks (and SQLite's serialized writes) make admission atomic across replicas.
Never trust a caller-supplied X-Forwarded-For header here.
"""
import time

from fastapi import HTTPException
from sqlalchemy import delete
from sqlalchemy.exc import SQLAlchemyError

from .config import settings
from .coordination import locked_state
from .database import SessionLocal
from .models import CoordinationState
from .security import digest

WINDOW = 300


def admit(address):
    window = int(time.time()) // WINDOW
    prefix = f"auth:{window:012d}:"
    retry = WINDOW - int(time.time()) % WINDOW
    try:
        with SessionLocal() as db:
            # All auth admission follows this lock order, including pruning.
            # At most global_limit distinct addresses can be admitted per window.
            global_row = locked_state(db, prefix + "global")
            db.execute(delete(CoordinationState).where(
                CoordinationState.key >= "auth:", CoordinationState.key < prefix))
            total = int(global_row.value.get("attempts", 0))
            if total >= settings.auth_global_limit:
                db.commit()
                raise HTTPException(429, "Sign-in capacity reached; retry later", headers={"Retry-After": str(retry)})
            global_row.value = {"attempts": total + 1}
            row = locked_state(db, prefix + digest(address))
            count = int(row.value.get("attempts", 0))
            allowed = count < settings.auth_address_limit
            row.value = {"attempts": min(count + 1, settings.auth_address_limit)}
            db.commit()
    except SQLAlchemyError:
        # Falling back to a per-process counter would multiply the budget.
        raise HTTPException(503, "Sign-in admission is temporarily unavailable", headers={"Retry-After": "5"}) from None
    if not allowed:
        raise HTTPException(429, "Too many sign-in attempts; retry later", headers={"Retry-After": str(retry)})
