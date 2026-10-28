"""Durable fair scheduling with synthetic sources and no network traffic."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app import worker
from app.models import Source, Task, User
from test_worker_reliability import isolated  # noqa: F401 -- isolated database fixture


def add_sources(db, owner, count, *, prefix="source", **changes):
    result = []
    for index in range(count):
        row = Source(owner_id=owner, kind="greenhouse", slug=f"{prefix}-{index}",
                     company="Synthetic employer", permitted=True, enabled=True,
                     interval_seconds=300, **changes)
        db.add(row)
        db.flush()
        result.append(row.id)
    return result


def test_small_source_groups_get_capacity_alongside_large_new_backlog(isolated, monkeypatch):  # noqa: F811
    owner, _ = isolated.account()
    monkeypatch.setattr(worker.settings, "crawl_batch_size", 3)
    old = (datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()
    with isolated.sessions() as db:
        add_sources(db, owner, 80, prefix="new")
        low = add_sources(db, owner, 8, prefix="small", last_attempt=old,
                          next_run=old, discovered_count=2)
        high = add_sources(db, owner, 8, prefix="large", last_attempt=old,
                           next_run=old, discovered_count=500)
        db.commit()
    assert worker.schedule_due() == 3
    with isolated.sessions() as db:
        chosen = {task.payload["source_id"] for task in db.scalars(select(Task))}
        assert len(chosen & set(low)) == 1
        assert len(chosen & set(high)) == 1
        assert len(chosen - set(low) - set(high)) == 1
    # Previously queued sources never repeatedly occupy the scheduling batch.
    assert worker.schedule_due() == 3
    with isolated.sessions() as db:
        all_chosen = [task.payload["source_id"] for task in db.scalars(select(Task))]
        assert len(all_chosen) == len(set(all_chosen)) == 6


def test_other_owner_is_not_starved_by_a_large_source_import(isolated, monkeypatch):  # noqa: F811
    large, _ = isolated.account()
    small, only = isolated.account(daily_preparation_limit=2)
    monkeypatch.setattr(worker.settings, "crawl_batch_size", 2)
    old = (datetime.now(timezone.utc)-timedelta(days=1)).isoformat()
    with isolated.sessions() as db:
        add_sources(db, large, 100, next_run=old)
        db.commit()
    assert worker.schedule_due() == 2
    with isolated.sessions() as db:
        tasks = list(db.scalars(select(Task)))
        assert {task.owner_id for task in tasks} == {large, small}
        assert only in {task.payload["source_id"] for task in tasks}


def test_paused_disabled_and_active_retries_cannot_fill_the_batch(isolated, monkeypatch):  # noqa: F811
    paused, _ = isolated.account(emergency_stop=True)
    disabled, _ = isolated.account(daily_preparation_limit=3)
    active, retry_id = isolated.account(daily_preparation_limit=4)
    monkeypatch.setattr(worker.settings, "crawl_batch_size", 2)
    old = (datetime.now(timezone.utc)-timedelta(days=1)).isoformat()
    future = (datetime.now(timezone.utc)+timedelta(hours=2)).isoformat()
    with isolated.sessions() as db:
        add_sources(db, paused, 20, next_run=old)
        add_sources(db, disabled, 20, next_run=old)
        db.get(User, disabled).disabled = True
        retry = db.get(Source, retry_id)
        retry.failures, retry.next_run = 2, old
        worker.enqueue(db, active, "discovery", {"source_id":retry_id}, f"source:{retry_id}")
        valid = add_sources(db, active, 2, next_run=old)
        blocked = add_sources(db, active, 1, failures=2, next_run=future)[0]
        db.commit()
    assert worker.schedule_due() == 2
    assert worker.schedule_due() == 0
    with isolated.sessions() as db:
        rows = list(db.scalars(select(Task)))
        assert len(rows) == 3
        assert {row.payload["source_id"] for row in rows} == set(valid + [retry_id])
        assert db.get(Source, retry_id).next_run == old
        assert db.get(Source, blocked).next_run == future


def test_unqueued_failed_source_keeps_server_backoff_until_actual_scan(isolated):  # noqa: F811
    _, source_id = isolated.account()
    old = (datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat()
    with isolated.sessions() as db:
        source = db.get(Source, source_id)
        source.failures, source.next_run = 1, old
        db.commit()
    assert worker.schedule_due() == 1
    assert worker.schedule_due() == 0
    with isolated.sessions() as db:
        assert db.get(Source, source_id).next_run == old
        assert len(list(db.scalars(select(Task)))) == 1
