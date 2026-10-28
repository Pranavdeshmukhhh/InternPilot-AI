"""Durable priority worker with leases and conservative restart recovery.

PostgreSQL supports concurrent replicas using SKIP LOCKED; SQLite uses atomic
compare-and-swap claims for a single-machine local deployment. No external
submission is retried after the durable final-click checkpoint.
"""
import asyncio
import logging
import os
import signal
import socket
import weakref
from pathlib import Path
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, update, func, delete, case, exists
from .config import settings
from .database import SessionLocal
from .migrate import migrate
from .models import Task, Source, User, Application, OutreachMessage, CrawlRun, now, uid
from .security import decrypt
from .services import enqueue, event, process_application, process_discovery, queue_automatic_preparation
from .monitoring import record_heartbeat
from .reminders import schedule_deadline_reminders

log = logging.getLogger("internpilot.worker")
_BROWSER_POOLS = weakref.WeakKeyDictionary()


def browser_pool():
    loop = asyncio.get_running_loop()
    if loop not in _BROWSER_POOLS:
        _BROWSER_POOLS[loop] = asyncio.Semaphore(settings.browser_concurrency)
    return _BROWSER_POOLS[loop]


def adaptive_capacity(previous):
    """Reduce pressure after measured source errors; recover one slot per interval."""
    if "discovery" not in settings.worker_kinds:
        return settings.concurrency
    with SessionLocal() as db:
        since = (datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat()
        outcomes = dict(db.execute(select(CrawlRun.outcome,func.count()).where(CrawlRun.started_at>=since,CrawlRun.outcome!="running").group_by(CrawlRun.outcome)).all())
    total = sum(outcomes.values())
    if total>=5 and outcomes.get("error",0)/total>.25:
        return max(1,previous//2)
    return min(settings.concurrency,previous+1)


def prune_scan_history():
    cutoff=(datetime.now(timezone.utc)-timedelta(days=settings.crawl_log_retention_days)).isoformat()
    with SessionLocal() as db:
        result=db.execute(delete(CrawlRun).where(CrawlRun.started_at<cutoff))
        db.commit()
        return result.rowcount


def prepare_notification_drafts():
    from .notification_delivery import materialize_delivery_drafts
    with SessionLocal() as db:
        count = materialize_delivery_drafts(db)
        db.commit()
        return count


def recover_expired():
    with SessionLocal() as db:
        rows = db.scalars(select(Task).where(Task.status=="running",Task.lease_until<now()).with_for_update(skip_locked=True)).all()
        for task in rows:
            if task.kind=="discovery":
                interrupted=db.scalars(select(CrawlRun).where(CrawlRun.owner_id==task.owner_id,CrawlRun.source_id==task.payload.get("source_id"),CrawlRun.outcome=="running"))
                for run in interrupted:
                    run.outcome,run.finished_at="error",now()
            if task.kind=="outreach":
                message = db.get(OutreachMessage,task.payload.get("message_id"))
                if message and message.sending_started_at:
                    if message.status=="sending":
                        message.status,message.reason,message.updated_at = "uncertain","Worker stopped after send checkpoint; reconcile the Gmail receipt before another action",now()
                    task.status,task.lease_owner,task.lease_until,task.updated_at = "completed",None,None,now()
                    continue
            app = db.get(Application,task.payload.get("application_id")) if task.kind=="application" else None
            if app and app.submission_started_at:
                if app.status=="submitting":
                    app.status, app.reason, app.updated_at = "uncertain","Worker stopped after submission checkpoint; reconcile confirmation before any further action",now()
                    event(db,app.owner_id,"uncertain",app.reason,app.id,notify=True)
                task.status = "completed"
            elif app and app.upload_started_at:
                app.status,app.reason,app.updated_at = "uncertain","Worker stopped after the upload checkpoint; reconcile the official form before any further upload",now()
                event(db,app.owner_id,"uncertain",app.reason,app.id,notify=True)
                task.status = "completed"
            elif app and app.status not in {"queued","preparing","approved"}:
                task.status = "completed"
            else:
                task.status = "queued"
                task.available_at = now()
                if app:
                    app.status = "approved" if app.approved_at else "queued"
                    app.reason = "Recovered safe preparation after worker lease expired"
                event(db,task.owner_id,"worker_recovery","Recovered pre-submission task after worker restart",app.id if app else None)
            task.lease_owner,task.lease_until,task.updated_at = None,None,now()
        db.commit()
        return len(rows)


def schedule_due():
    with SessionLocal() as db:
        at = now()
        filters = (Source.enabled==True, Source.permitted==True,
                   (Source.next_run==None) | (Source.next_run<=at))
        # Accounts paused by their owner must not consume a bounded scheduling
        # batch. Read only the policies of accounts with due sources.
        accounts = db.execute(select(User.id, User.policy_encrypted).join(
            Source, Source.owner_id==User.id).where(User.disabled==False, *filters).distinct()).all()
        allowed = []
        for owner_id, policy in accounts:
            try:
                if not decrypt(policy).get("emergency_stop", False):
                    allowed.append(owner_id)
            except Exception as exc:
                log.error("Cannot schedule an account's sources (%s)", type(exc).__name__)
        if not allowed:
            return 0
        # Rotate between owners and source-volume groups before taking another
        # source from the same group. The count describes observed records, not
        # employer size. No famous-employer preference or inferred quality score.
        # NULL schedules are newly configured sources and become due *now*, so
        # continuously added sources cannot displace already overdue small ones.
        tier = case((Source.last_attempt==None, 0), (Source.discovered_count<=10, 1), else_=2)
        due_at = func.coalesce(Source.next_run, Source.last_attempt, at)
        active = exists(select(Task.id).where(
            Task.dedupe_key=="source:" + Source.id, Task.status.in_(("queued", "running"))))
        ranked = select(Source.id.label("id"), due_at.label("due_at"),
            func.row_number().over(partition_by=(Source.owner_id, tier),
                order_by=(due_at, Source.id)).label("turn")).where(
                    *filters, Source.owner_id.in_(allowed), ~active).subquery()
        # Lock only sources, not the window subquery (PostgreSQL forbids locking
        # a SELECT containing windows). Other scheduler replicas skip held rows.
        due = list(db.scalars(select(Source).join(ranked, ranked.c.id==Source.id)
            .order_by(ranked.c.turn, ranked.c.due_at, Source.id)
            .with_for_update(skip_locked=True, of=Source).limit(settings.crawl_batch_size)))
        for source in due:
            user = db.get(User,source.owner_id)
            if not user or user.disabled:
                continue
            try:
                if decrypt(user.policy_encrypted).get("emergency_stop", False):
                    continue
            except Exception as exc:
                log.error("Cannot schedule an account's sources (%s)", type(exc).__name__)
                continue
            enqueue(db,user.id,"discovery",{"source_id":source.id},f"source:{source.id}")
            if not source.failures:
                source.next_run = (datetime.now(timezone.utc)+timedelta(seconds=source.interval_seconds)).isoformat()
        db.commit()
        return len(due)


def claim_task(worker_id):
    with SessionLocal() as db:
        candidate = db.scalar(select(Task).where(Task.status=="queued",Task.available_at<=now(),Task.kind.in_(settings.worker_kinds)).order_by(Task.priority.desc(),Task.created_at).with_for_update(skip_locked=True).limit(1))
        if not candidate:
            return None
        lease = (datetime.now(timezone.utc)+timedelta(seconds=settings.task_lease_seconds)).isoformat()
        result = db.execute(update(Task).where(Task.id==candidate.id,Task.status=="queued").values(status="running",lease_owner=worker_id,lease_until=lease,attempts=Task.attempts+1,updated_at=now()).execution_options(synchronize_session=False))
        db.commit()
        if result.rowcount!=1:
            return None
        db.refresh(candidate)
        return {"id":candidate.id,"owner_id":candidate.owner_id,"kind":candidate.kind,"payload":candidate.payload,"attempts":candidate.attempts}


async def heartbeat(task_id,worker_id):
    while True:
        await asyncio.sleep(max(5,settings.task_lease_seconds//3))
        try:
            with SessionLocal() as db:
                result = db.execute(update(Task).where(Task.id==task_id,Task.status=="running",Task.lease_owner==worker_id,Task.lease_until>now()).values(lease_until=(datetime.now(timezone.utc)+timedelta(seconds=settings.task_lease_seconds)).isoformat(),updated_at=now()))
                db.commit()
                if not result.rowcount:
                    return  # A lost or expired lease must never be revived.
        except Exception as exc:
            log.error("Task lease heartbeat failed (%s)", type(exc).__name__)


async def execute_task(task, worker_id):
    pulse = asyncio.create_task(heartbeat(task["id"],worker_id))
    try:
        if task["kind"]=="discovery":
            await process_discovery(task["owner_id"],task["payload"].get("source_id"))
        elif task["kind"]=="application":
            async with browser_pool():
                await process_application(task["payload"]["application_id"],task_id=task["id"],lease_owner=worker_id,automatic=bool(task["payload"].get("automatic_preparation")))
        elif task["kind"]=="outreach":
            from .outreach import send_message
            await send_message(task["payload"]["message_id"],task_id=task["id"],lease_owner=worker_id)
        elif task["kind"]=="gmail_sync":
            from .outreach import sync_replies
            await sync_replies(task["owner_id"])
        else:
            raise ValueError("Unsupported task kind")
        with SessionLocal() as db:
            db.execute(update(Task).where(Task.id==task["id"],Task.lease_owner==worker_id,Task.status=="running").values(status="completed",lease_owner=None,lease_until=None,updated_at=now()))
            db.commit()
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        with SessionLocal() as db:
            row = db.get(Task,task["id"])
            if row and row.status=="running" and row.lease_owner==worker_id:
                app = db.get(Application,task["payload"].get("application_id")) if task["kind"]=="application" else None
                if app and app.submission_started_at:
                    if app.status=="submitting":
                        app.status,app.reason = "uncertain","Worker failed after submit checkpoint; reconcile confirmation manually"
                        app.updated_at = now()
                    row.status = "failed"
                elif app and app.upload_started_at:
                    app.status,app.reason,app.updated_at = "uncertain","Worker failed after the upload checkpoint; reconcile the official form before any further upload",now()
                    row.status = "failed"
                elif task["attempts"]<3:
                    row.status = "queued"
                    row.available_at = (datetime.now(timezone.utc)+timedelta(seconds=5*2**task["attempts"])).isoformat()
                else:
                    row.status = "failed"
                row.error = f"{type(exc).__name__}: task failed; inspect source health or application record"
                row.lease_owner,row.lease_until,row.updated_at = None,None,now()
                event(db,row.owner_id,"worker_error",row.error,app.id if app else None,notify=True)
                db.commit()
    finally:
        pulse.cancel()
        await asyncio.gather(pulse,return_exceptions=True)


def maintenance(name, operation, *args, **kwargs):
    """Best-effort housekeeping must not stop the durable execution loop."""
    try:
        return operation(*args, **kwargs)
    except Exception as exc:
        log.error("Worker %s failed (%s); continuing", name, type(exc).__name__)
        return None


def completed_task(task, running):
    running.discard(task)
    if not task.cancelled():
        # execute_task can still fail if the error-recovery transaction fails.
        # Observe that exception; the durable lease will recover the task later.
        error = task.exception()
        if error:
            log.error("Task execution interrupted (%s); durable lease recovery remains active", type(error).__name__)


async def drain_tasks(running):
    """Give in-flight work a bounded shutdown and observe every outcome."""
    if not running:
        return
    tasks = set(running)
    try:
        await asyncio.wait(tasks, timeout=20)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def run_worker():
    migrate()
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT,signal.SIGTERM):
        try:
            loop.add_signal_handler(sig,stopped.set)
        except (NotImplementedError,RuntimeError):
            pass  # Windows Ctrl+C still terminates and lease recovery is safe.
    worker_id = f"{socket.gethostname()}:{os.getpid()}:{uid()}"
    running = set()
    tick = 0
    capacity = settings.concurrency
    log.info("Durable worker started with concurrency=%s",settings.concurrency)
    try:
        while not stopped.is_set():
            if tick%3600==0 and "discovery" in settings.worker_kinds:
                maintenance("scan history retention",prune_scan_history)
            if tick%30==0:
                capacity = maintenance("adaptive capacity",adaptive_capacity,capacity) or capacity
            if tick%5==0:
                maintenance("presence heartbeat", record_heartbeat, worker_id, capacity)
            if tick%300==0:
                if "discovery" in settings.worker_kinds:
                    maintenance("deadline reminders", schedule_deadline_reminders)
            if tick%15==0:
                maintenance("expired lease recovery", recover_expired)
                if "discovery" in settings.worker_kinds:
                    maintenance("source scheduling", schedule_due)
                maintenance("notification drafts", prepare_notification_drafts)
                if {"outreach","gmail_sync"}.intersection(settings.worker_kinds):
                    from .outreach import schedule_outreach
                    maintenance("outreach scheduling",schedule_outreach)
            if tick%60==0:
                if "application" in settings.worker_kinds:
                    maintenance("automatic preparation", queue_automatic_preparation)
            while len(running)<capacity:
                task = maintenance("task claim", claim_task, worker_id)
                if not task:
                    break
                execution = asyncio.create_task(execute_task(task,worker_id))
                running.add(execution)
                execution.add_done_callback(lambda finished: completed_task(finished, running))
            if settings.worker_heartbeat_file:
                maintenance("supervisor heartbeat", Path(settings.worker_heartbeat_file).touch, mode=0o600)
            tick += 1
            try:
                await asyncio.wait_for(stopped.wait(),timeout=1)
            except TimeoutError:
                pass
    finally:
        try:
            await drain_tasks(running)
        finally:
            maintenance("stopped heartbeat", record_heartbeat, worker_id, settings.concurrency, stopped=True)


if __name__ == "__main__":
    from .logging_config import configure
    configure()
    asyncio.run(run_worker())
