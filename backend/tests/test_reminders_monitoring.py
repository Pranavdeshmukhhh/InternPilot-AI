"""Deadline notifications and actual worker presence across durable sessions."""
from datetime import datetime, timedelta, timezone
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import select, func
from app import monitoring, reminders
from app.models import WorkerHeartbeat, DeadlineReminder, Notification, Task, Application, User, Opportunity, SourceOpportunity, Source
from app.schemas import Policy
from app.security import decrypt, encrypt
from test_service_guards import isolated_services  # noqa: F401 -- pytest fixture registration


@pytest.fixture
def workspace(isolated_services, monkeypatch):
    monkeypatch.setattr(monitoring, "SessionLocal", isolated_services.sessions)
    monkeypatch.setattr(reminders, "SessionLocal", isolated_services.sessions)
    return isolated_services


def add_job(workspace, owner, source, *, hours=12, title="Engineering Internship", **changes):
    deadline = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()
    data = {"title": title, "company": "Test Employer", "url": "https://example.invalid/jobs/" + title,
            "description": "Undergraduate internship for students graduating in 2029. Python. Open to applicants in India.",
            "requirements": {"graduation_years": [2029], "degree_levels": ["undergraduate"], "countries": ["India"]},
            "location": "India", "remote": True, "active": True, "deadline": deadline, **changes}
    with workspace.sessions() as db:
        user = db.get(User, owner)
        policy = Policy.model_validate(decrypt(user.policy_encrypted)).model_dump()
        policy["deadline_minimum_score"] = 0
        user.policy_encrypted = encrypt(policy)
        job = Opportunity(fingerprint=title+owner, data=data)
        db.add(job); db.flush()
        db.add(SourceOpportunity(source_id=source, opportunity_id=job.id))
        db.commit()
        return job.id


def test_deadline_reminder_is_durable_owned_and_deduplicated(workspace):
    owner, source = workspace.add_account("deadline-owner")
    other, _ = workspace.add_account("deadline-other")
    job_id = add_job(workspace, owner, source)
    assert reminders.schedule_deadline_reminders() == 1
    assert reminders.schedule_deadline_reminders() == 0
    with workspace.sessions() as db:
        notifications = list(db.scalars(select(Notification)))
        assert len(notifications) == 1
        assert notifications[0].owner_id == owner
        assert notifications[0].opportunity_id == job_id
        assert notifications[0].kind == "deadline_reminder"
        assert "closes" in notifications[0].message and "UTC" in notifications[0].message
        assert db.scalar(select(func.count()).select_from(DeadlineReminder)) == 1
        assert db.scalar(select(func.count()).select_from(Notification).where(Notification.owner_id == other)) == 0
        notifications[0].read = True
        db.commit()
    # Reading a notice or a worker restart cannot make it send again.
    assert reminders.schedule_deadline_reminders() == 0


@pytest.mark.parametrize("changes,hours", [
    ({"active": False}, 12), ({"is_demo": True}, 12), ({"deadline": None}, 12),
    ({}, -1), ({}, 90),
    ({"description": "Only students graduating in 2028 are eligible.", "requirements": {"graduation_years": [2028]}}, 12),
])
def test_unsuitable_or_unknown_deadlines_do_not_alert(workspace, changes, hours):
    owner, source = workspace.add_account("no-deadline-alert")
    add_job(workspace, owner, source, hours=hours, **changes)
    assert reminders.schedule_deadline_reminders() == 0


def test_deadline_preference_and_existing_application_are_respected(workspace):
    owner, source = workspace.add_account("already-applied")
    job_id = add_job(workspace, owner, source)
    with workspace.sessions() as db:
        db.add(Application(owner_id=owner, opportunity_id=job_id))
        db.commit()
    assert reminders.schedule_deadline_reminders() == 0
    add_job(workspace, owner, source, title="Second Internship")
    with workspace.sessions() as db:
        user = db.get(User, owner)
        policy = Policy.model_validate(decrypt(user.policy_encrypted)).model_dump()
        policy["deadline_reminders"] = False
        user.policy_encrypted = encrypt(policy)
        db.commit()
    assert reminders.schedule_deadline_reminders() == 0


def test_stale_or_disabled_sources_do_not_generate_deadline_alerts(workspace):
    owner, source = workspace.add_account("disabled-source")
    job_id = add_job(workspace, owner, source)
    with workspace.sessions() as db:
        db.get(Source, source).enabled = False
        db.commit()
    assert reminders.schedule_deadline_reminders() == 0
    with workspace.sessions() as db:
        db.get(Source, source).enabled = True
        db.get(Opportunity, job_id).last_verified = (datetime.now(timezone.utc) - timedelta(hours=49)).isoformat()
        db.commit()
    assert reminders.schedule_deadline_reminders() == 0


def test_deadline_alerts_are_earliest_first_and_rate_limited(workspace):
    owner, source = workspace.add_account("many-deadlines")
    for i in range(12):
        add_job(workspace, owner, source, hours=20-i, title=f"Internship {i}")
    assert reminders.schedule_deadline_reminders() == 5
    with workspace.sessions() as db:
        notices = list(db.scalars(select(Notification).order_by(Notification.created_at)))
        assert "Internship 11" in notices[0].message
    assert reminders.schedule_deadline_reminders() == 5
    assert reminders.schedule_deadline_reminders() == 0


def test_changed_deadline_can_alert_again_but_policy_score_filters(workspace):
    owner, source = workspace.add_account("changed-deadline")
    job_id = add_job(workspace, owner, source)
    assert reminders.schedule_deadline_reminders() == 1
    with workspace.sessions() as db:
        row = db.get(Opportunity, job_id)
        row.data = {**row.data, "deadline": (datetime.now(timezone.utc) + timedelta(hours=13)).isoformat()}
        user = db.get(User, owner)
        policy = Policy.model_validate(decrypt(user.policy_encrypted)).model_dump()
        policy["deadline_minimum_score"] = 100
        user.policy_encrypted = encrypt(policy)
        db.commit()
    assert reminders.schedule_deadline_reminders() == 0
    with workspace.sessions() as db:
        user = db.get(User, owner)
        policy = decrypt(user.policy_encrypted); policy["deadline_minimum_score"] = 0
        user.policy_encrypted = encrypt(policy); db.commit()
    assert reminders.schedule_deadline_reminders() == 1


def test_worker_presence_expires_and_queue_counts_are_owner_scoped(workspace):
    owner, _ = workspace.add_account("worker-owner")
    other, _ = workspace.add_account("worker-other")
    with workspace.sessions() as db:
        db.add(Task(owner_id=owner, kind="discovery", dedupe_key="owner-queued", payload={}, status="queued"))
        db.add(Task(owner_id=other, kind="discovery", dedupe_key="other-queued", payload={}, status="queued"))
        db.commit()
        assert monitoring.worker_status(db, owner)["status"] == "offline"
    monitoring.record_heartbeat("synthetic-worker", 2)
    with workspace.sessions() as db:
        status = monitoring.worker_status(db, owner)
        assert status["status"] == "online" and status["capacity"] == 2
        assert status["queued"] == 1 and status["running"] == 0
        row = db.get(WorkerHeartbeat, "synthetic-worker")
        row.last_seen = (datetime.now(timezone.utc) - timedelta(seconds=90)).isoformat()
        db.commit()
        assert monitoring.worker_status(db, owner)["status"] == "offline"
    monitoring.record_heartbeat("synthetic-worker", 2, stopped=True)
    with workspace.sessions() as db:
        assert monitoring.worker_status(db, owner)["status"] == "offline"


def test_version_one_database_migrates_without_losing_notices(tmp_path):
    script = """
import json
from sqlalchemy import text,inspect
from app.database import Base,engine
from app import models
from app.migrate import migrate
Base.metadata.create_all(engine)
with engine.begin() as c:
 c.execute(text('DROP TABLE worker_heartbeats'))
 c.execute(text('DROP TABLE deadline_reminders'))
 c.execute(text('ALTER TABLE notifications DROP COLUMN opportunity_id'))
 c.execute(text("INSERT INTO schema_versions(version,applied_at) VALUES (1,'2026-10-01')"))
 c.execute(text("INSERT INTO notifications(id,owner_id,message,kind,read,created_at) VALUES ('old','owner','Preserved notice','existing',0,'2026-10-01')"))
migrate();migrate()
with engine.connect() as c:
 assert list(c.execute(text('SELECT version FROM schema_versions ORDER BY version')).scalars())==[1,2,3,4,5,6,7]
 assert c.execute(text("SELECT message, opportunity_id FROM notifications WHERE id='old'")).one()==('Preserved notice',None)
 assert {'worker_heartbeats','deadline_reminders'}.issubset(set(inspect(c).get_table_names()))
print('version-1 upgrade preserved existing records')
"""
    env = {**os.environ, "DATA_DIR": str(tmp_path), "DATABASE_URL": f"sqlite:///{tmp_path/'migration.db'}", "ENVIRONMENT": "development", "DATABASE_SSLMODE": ""}
    result = subprocess.run([sys.executable, "-c", script], cwd=Path(__file__).parents[1], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
