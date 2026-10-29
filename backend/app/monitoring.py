"""Durable worker presence for the dashboard and process supervisors."""
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, delete, func
from .database import SessionLocal
from .models import WorkerHeartbeat, Task, now


def record_heartbeat(worker_id, concurrency, *, stopped=False):
    with SessionLocal() as db:
        row = db.get(WorkerHeartbeat, worker_id)
        if row is None:
            row = WorkerHeartbeat(id=worker_id, concurrency=concurrency, last_seen=now(), stopped=stopped)
            db.add(row)
        else:
            row.last_seen, row.concurrency, row.stopped = now(), concurrency, stopped
        # Presence records are operational data; audit events remain untouched.
        cutoff = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        db.execute(delete(WorkerHeartbeat).where(WorkerHeartbeat.last_seen < cutoff))
        db.commit()


def worker_status(db, owner_id):
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
    workers = list(db.scalars(select(WorkerHeartbeat).where(WorkerHeartbeat.last_seen >= cutoff, WorkerHeartbeat.stopped == False)))
    last_seen = db.scalar(select(func.max(WorkerHeartbeat.last_seen)))
    counts = dict(db.execute(select(Task.status, func.count()).where(Task.owner_id == owner_id).group_by(Task.status)).all())
    from .models import CoordinationState
    control = db.get(CoordinationState, "workers")
    return {"control":control.value if control else {"paused":False,"paused_kinds":[]}, "status": "online" if workers else "offline", "active_workers": len(workers),
            "capacity": sum(w.concurrency for w in workers), "last_seen": last_seen,
            "queued": counts.get("queued", 0), "running": counts.get("running", 0),
            "failed": counts.get("failed", 0)}
