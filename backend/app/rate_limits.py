"""PostgreSQL host budgets shared by every crawler replica; local mode stays local."""
import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .config import settings
from .database import SessionLocal
from .models import HostBudget


def reserve(host,delay,*,cooldown=False):
    instant = datetime.now(timezone.utc)
    with SessionLocal() as db:
        row = db.scalar(select(HostBudget).where(HostBudget.host==host).with_for_update())
        if row is None:
            try:
                with db.begin_nested():
                    db.add(HostBudget(host=host,next_allowed=instant.isoformat()))
                    db.flush()
            except IntegrityError:
                pass
            row = db.scalar(select(HostBudget).where(HostBudget.host==host).with_for_update().execution_options(populate_existing=True))
        available = datetime.fromisoformat(row.next_allowed)
        if cooldown or available<=instant:
            row.next_allowed = max(available,instant+timedelta(seconds=delay)).isoformat()
            db.commit()
            return 0.0
        return min(86400,max(0.0,(available-instant).total_seconds()))


def enabled():
    return settings.distributed_rate_limits and settings.database_url.startswith("postgresql")


async def throttle(host,delay):
    if not enabled():
        return
    waited = 0.0
    while True:
        wait = await asyncio.to_thread(reserve,host,max(1.0,delay))
        if wait<=0:
            return
        if waited+wait>60:
            from .discovery import DiscoveryError
            raise DiscoveryError("Shared source host budget is busy; reschedule without exceeding its rate limit",retry_after=max(5,int(wait)))
        await asyncio.sleep(wait)
        waited += wait


async def cooldown(host,seconds):
    if enabled():
        await asyncio.to_thread(reserve,host,seconds,cooldown=True)
