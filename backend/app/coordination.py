"""Database-authoritative admission. Redis is never required for correctness."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import random
import weakref
from uuid import uuid4

from sqlalchemy import select, update, delete, func

from .config import settings
from .database import SessionLocal
from .models import CoordinationState, RequestLease, DiscoveryHealth, Task, now


_LOCAL_POOLS = weakref.WeakKeyDictionary()


class QueueCapacityError(ValueError):
    pass


def locked_state(db, key):
    from .catalog import insert_for
    stmt = insert_for(db, CoordinationState.__table__).values(key=key, value={})
    db.execute(stmt.on_conflict_do_nothing(index_elements=["key"]))
    # The write also serializes SQLite callers, where FOR UPDATE is unavailable.
    db.execute(update(CoordinationState).where(CoordinationState.key == key).values(key=key))
    return db.scalar(select(CoordinationState).where(CoordinationState.key == key).with_for_update().execution_options(populate_existing=True))


def admit_task(db, owner):
    locked_state(db, "queue-admission")
    pending = Task.status.in_(("queued", "running"))
    total = db.scalar(select(func.count()).select_from(Task).where(pending))
    own = db.scalar(select(func.count()).select_from(Task).where(pending, Task.owner_id == owner))
    if total >= settings.queue_max_pending or own >= settings.queue_owner_pending:
        raise QueueCapacityError("Queue capacity reached; existing work is preserved. Retry later.")


def paused(db, kind):
    row = db.get(CoordinationState, "workers")
    return bool(row and (row.value.get("paused") or kind in row.value.get("paused_kinds", [])))


def request_slot(host):
    with SessionLocal() as db:
        locked_state(db, "http-admission")
        db.execute(delete(RequestLease).where(RequestLease.expires_at <= now()))
        global_count = db.scalar(select(func.count()).select_from(RequestLease))
        host_count = db.scalar(select(func.count()).select_from(RequestLease).where(RequestLease.host == host))
        policy = settings.http_host_policies.get(host, {})
        host_limit = max(1, min(settings.http_host_concurrency, int(policy.get("concurrency", settings.http_host_concurrency))))
        if global_count >= settings.http_global_concurrency or host_count >= host_limit:
            db.commit()
            return None
        token = str(uuid4())
        db.add(RequestLease(id=token, host=host, expires_at=(datetime.now(timezone.utc) + timedelta(seconds=settings.http_request_timeout + 15)).isoformat()))
        db.commit()
        return token


def release_slot(token):
    with SessionLocal() as db:
        db.execute(delete(RequestLease).where(RequestLease.id == token)); db.commit()


@asynccontextmanager
async def http_slot(host):
    if not settings.database_url.startswith("postgresql"):
        loop = asyncio.get_running_loop()
        pool = _LOCAL_POOLS.setdefault(loop, asyncio.Semaphore(settings.http_global_concurrency))
        async with pool:
            yield
        return
    token = await asyncio.to_thread(request_slot, host)
    if token is None:
        from .discovery import DiscoveryError
        raise DiscoveryError("HTTP concurrency budget busy; deferred", retry_after=5)
    try:
        yield
    finally:
        # Completion/cancellation releases capacity; killed processes expire it.
        cleanup = asyncio.create_task(asyncio.to_thread(release_slot, token))
        await asyncio.shield(cleanup)


def retry_delay(attempt, base=5, maximum=86400):
    ceiling = min(maximum, base * 2 ** min(attempt, 16))
    return random.uniform(ceiling / 2, ceiling)


def health_ready(db, key):
    row = db.get(DiscoveryHealth, key)
    return not row or not row.next_attempt or row.next_attempt <= now()


def health_failure(db, key, exc, interval):
    from .catalog import insert_for
    stmt = insert_for(db, DiscoveryHealth.__table__).values(key=key, failures=0, checkpoint={})
    db.execute(stmt.on_conflict_do_nothing(index_elements=["key"]))
    row = db.scalar(select(DiscoveryHealth).where(DiscoveryHealth.key == key).with_for_update().execution_options(populate_existing=True))
    row.failures += 1
    delay = max(retry_delay(row.failures, base=max(5, interval)), float(getattr(exc, "retry_after", 0) or 0))
    # Permissions/config errors are deliberately slow; never probe through a block.
    if getattr(exc, "permanent", False):
        delay = max(delay, 86400)
    row.next_attempt = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()
    row.last_checked, row.last_error = now(), type(exc).__name__
    return row.next_attempt


def health_success(db, key):
    row = db.get(DiscoveryHealth, key)
    if row:
        row.failures, row.next_attempt, row.last_error, row.last_checked = 0, None, None, now()


def reserve_inference():
    """Fail closed on budget/DB outages; requests count even if provider fails."""
    with SessionLocal() as db:
        row = locked_state(db, "inference:" + datetime.now(timezone.utc).date().isoformat())
        used = int(row.value.get("requests", 0))
        if used >= settings.llm_daily_request_limit:
            return False
        row.value = {"requests":used + 1}
        db.commit()
        return True
