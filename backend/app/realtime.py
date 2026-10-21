"""Optional Redis wakeups after durable commits; DB remains the event source."""
import json
from sqlalchemy import event as sa_event
from sqlalchemy.orm import Session
from .config import settings


@sa_event.listens_for(Session,"after_commit")
def publish_committed(session):
    updates = session.info.pop("realtime_updates",set())
    if not settings.redis_url or not updates or session.in_nested_transaction():
        return
    try:
        from redis import Redis
        with Redis.from_url(settings.redis_url,socket_connect_timeout=0.3,socket_timeout=0.3) as client:
            for owner_id in updates:
                client.publish(f"internpilot:{owner_id}",json.dumps({"event":"refresh"}))
    except Exception:
        pass  # The stream polls durable events when Redis is unavailable.


@sa_event.listens_for(Session,"after_rollback")
def discard_rolled_back(session):
    if not session.in_nested_transaction():
        session.info.pop("realtime_updates",None)
