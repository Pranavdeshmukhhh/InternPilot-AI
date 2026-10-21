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
from pathlib import Path
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, update
from .config import settings
from .database import SessionLocal
from .migrate import migrate
from .models import Task, Source, User, Application, now, uid
from .security import decrypt
from .services import enqueue, event, process_application, process_discovery, queue_automatic_preparation
from .monitoring import record_heartbeat
from .reminders import schedule_deadline_reminders

log = logging.getLogger("internpilot.worker")


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
        due = list(db.scalars(select(Source).where(Source.enabled==True,Source.permitted==True, (Source.next_run==None) | (Source.next_run<=now())).with_for_update(skip_locked=True)))
        for source in due:
            user = db.get(User,source.owner_id)
            if not user:
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


def claim_task(worker_id):
    with SessionLocal() as db:
        candidate = db.scalar(select(Task).where(Task.status=="queued",Task.available_at<=now()).order_by(Task.priority.desc(),Task.created_at).with_for_update(skip_locked=True).limit(1))
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
            await process_application(task["payload"]["application_id"],task_id=task["id"],lease_owner=worker_id,automatic=bool(task["payload"].get("automatic_preparation")))
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
    log.info("Durable worker started with concurrency=%s",settings.concurrency)
    try:
        while not stopped.is_set():
            if tick%5==0:
                maintenance("presence heartbeat", record_heartbeat, worker_id, settings.concurrency)
            if tick%300==0:
                maintenance("deadline reminders", schedule_deadline_reminders)
            if tick%15==0:
                maintenance("expired lease recovery", recover_expired)
                maintenance("source scheduling", schedule_due)
                maintenance("notification drafts", prepare_notification_drafts)
            if tick%60==0:
                maintenance("automatic preparation", queue_automatic_preparation)
            while len(running)<settings.concurrency:
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
    logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(run_worker())
