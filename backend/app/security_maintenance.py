"""Run daily by a private operator scheduler. Bounded security retention cleanup."""
from datetime import datetime, timedelta, timezone
from sqlalchemy import delete, select
from .database import SessionLocal
from .models import SecurityEvent, PasswordRecovery, CoordinationState, LoginSession, now


def prune(db, limit=1000):
    cutoff=(datetime.now(timezone.utc)-timedelta(days=30)).isoformat()
    deleted={}
    for model,key,predicate in [
        (SecurityEvent,SecurityEvent.id,SecurityEvent.created_at<cutoff),
        (PasswordRecovery,PasswordRecovery.token_hash,PasswordRecovery.expires_at<cutoff),
        (LoginSession,LoginSession.token_hash,LoginSession.expires_at<now()),
        (CoordinationState,CoordinationState.key,CoordinationState.key.startswith('founder-unlock:') & (CoordinationState.value['until'].as_string()<now())),
    ]:
        identifiers=list(db.scalars(select(key).where(predicate).limit(limit)))
        deleted[model.__tablename__]=len(identifiers)
        if identifiers:db.execute(delete(model).where(key.in_(identifiers)))
    db.commit()
    return deleted


if __name__=='__main__':
    with SessionLocal() as session:
        print(prune(session))
