"""Bounded founder projections; no arbitrary SQL, credentials, or provider bodies."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from .config import settings
from .models import User, LoginSession, SecurityEvent, Application, Task, Source, WorkerHeartbeat, AuditEvent, now
from .security import decrypt


def report(db, section):
    cutoff=(datetime.now(timezone.utc)-timedelta(days=30)).isoformat()
    if section in {'overview','analytics'}:
        daily=db.execute(select(func.substr(User.created_at,1,10),func.count()).where(User.created_at>=cutoff)
                         .group_by(func.substr(User.created_at,1,10)).order_by(func.substr(User.created_at,1,10))).all()
        return {'members':db.scalar(select(func.count()).select_from(User)),
                'active_sessions':db.scalar(select(func.count()).select_from(LoginSession).where(LoginSession.expires_at>now())),
                'locked_accounts':db.scalar(select(func.count()).select_from(User).where(User.disabled==True)),
                'password_resets_required':db.scalar(select(func.count()).select_from(User).where(User.reset_required==True)),
                'new_members_30d':sum(value for _,value in daily),
                'registrations_by_day':[{'date':day,'count':value} for day,value in daily],
                'application_statuses':dict(db.execute(select(Application.status,func.count()).group_by(Application.status)).all())}
    if section in {'activity','security'}:
        rows=db.execute(select(SecurityEvent,User.email_encrypted).outerjoin(User,User.id==SecurityEvent.user_id)
                        .order_by(SecurityEvent.created_at.desc(),SecurityEvent.id).limit(100)).all()
        audit=[{'id':row.id,'user_id':row.owner_id,'kind':row.kind,'at':row.created_at} for row in db.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc(),AuditEvent.id).limit(100))] if section=='activity' else []
        return {'audit':audit,'events':[{'id':row.id,'user_id':row.user_id,'email':decrypt(email) if email else None,
                           'kind':row.kind,'address_tag':row.address_tag,'at':row.created_at} for row,email in rows],
                'failed_logins_30d':db.scalar(select(func.count()).select_from(SecurityEvent).where(SecurityEvent.created_at>=cutoff,SecurityEvent.kind.in_(('login_failed','mfa_failed','login_locked')))),
                'classification':'Failed attempts are signals for review, not proof of malicious activity', 'limit':100}
    if section=='applications':
        rows=db.execute(select(Application.id,Application.owner_id,Application.status,Application.created_at,User.email_encrypted)
                        .join(User,User.id==Application.owner_id).order_by(Application.created_at.desc(),Application.id).limit(100)).all()
        return {'applications':[{'id':identifier,'user_id':owner,'email':decrypt(email),'status':status,'at':stamp} for identifier,owner,status,stamp,email in rows],'limit':100}
    if section in {'automation','infrastructure'}:
        workers=db.scalars(select(WorkerHeartbeat).order_by(WorkerHeartbeat.last_seen.desc()).limit(50)).all()
        stale=(datetime.now(timezone.utc)-timedelta(seconds=60)).isoformat()
        return {'queue':dict(db.execute(select(Task.status,func.count()).group_by(Task.status)).all()),
                'sources':dict(db.execute(select(Source.status,func.count()).group_by(Source.status)).all()),
                'workers':[{'id':row.id,'last_seen':row.last_seen,'concurrency':row.concurrency,
                            'status':'stopped' if row.stopped else 'stale' if row.last_seen<stale else 'recent heartbeat'} for row in workers],
                'database':db.get_bind().dialect.name,'database_query':'ok','redis_configured':bool(settings.redis_url),
                'note':'A database response and recent heartbeat are observations, not a cloud availability guarantee'}
    return {'invitation_only':settings.invitation_only,'activation_open':settings.allow_registration,
            'secure_cookies':settings.cookie_secure,'production':settings.production,
            'founder_limit':1,'report_reauthentication_minutes':5,
            'secrets':'Deployment credentials are managed outside this dashboard'}
