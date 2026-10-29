"""In-app deadline alerts, deduplicated durably across worker restarts."""
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func, or_
from sqlalchemy.exc import IntegrityError
from .database import SessionLocal
from .models import User, Application, DeadlineReminder, Notification, Opportunity
from .security import decrypt, digest
from .services import job_view, timestamp, event, permitted_opportunity_ids
from .schemas import Policy


def schedule_deadline_reminders(at=None):
    at = at or datetime.now(timezone.utc)
    sent = 0
    with SessionLocal() as db:
        users = db.scalars(select(User).with_for_update(skip_locked=True)).all()
        for user in users:
            policy = Policy.model_validate(decrypt(user.policy_encrypted))
            if not policy.deadline_reminders:
                continue
            today = at.date().isoformat()
            used = db.scalar(select(func.count()).select_from(Notification).where(Notification.owner_id == user.id, Notification.kind == "deadline_reminder", Notification.created_at >= today))
            allowance = min(5, max(0, 10 - used))
            if not allowance:
                continue
            profile = decrypt(user.profile_encrypted)
            histories = list(db.execute(select(Application.opportunity_id, Opportunity.canonical_id, Opportunity.url_key)
                .join(Opportunity, Opportunity.id == Application.opportunity_id).where(Application.owner_id == user.id)))
            applied = {ident for original, canonical, _ in histories for ident in (original, canonical) if ident}
            applied_urls = {key for _, _, key in histories if key}
            candidates = []
            from .catalog_query import visible_ids
            jobs = list(db.scalars(select(Opportunity).where(Opportunity.id.in_(visible_ids(user.id)),
                or_(Opportunity.projection_version != 1, (Opportunity.deadline_at > at) & (Opportunity.deadline_at <= at + timedelta(hours=policy.deadline_reminder_hours))))))
            permitted = permitted_opportunity_ids(db, user.id, [job.id for job in jobs])
            for job in jobs:
                deadline = timestamp(job.data.get("deadline"))
                verified_at = timestamp(job.last_verified)
                if job.id not in permitted or job.id in applied or job.url_key and job.url_key in applied_urls or job.data.get("is_demo") or job.data.get("active") is False or not deadline:
                    continue
                if not verified_at or verified_at < at - timedelta(hours=48):
                    continue
                if not at < deadline <= at + timedelta(hours=policy.deadline_reminder_hours):
                    continue
                view = job_view(job, profile)
                if view["eligibility"] == "ineligible" or view["score"] < policy.deadline_minimum_score:
                    continue
                candidates.append((deadline, job, view))
            for deadline, job, view in sorted(candidates, key=lambda row: row[0]):
                reminder_id = digest(f"{user.id}:{job.id}:{deadline.isoformat()}")
                try:
                    with db.begin_nested():
                        db.add(DeadlineReminder(id=reminder_id, owner_id=user.id, opportunity_id=job.id, deadline_at=deadline.isoformat()))
                        db.flush()
                except IntegrityError:
                    continue
                qualification = "Eligibility needs your review." if view["eligibility"] == "review" else "Matches your verified eligibility."
                message = f"{job.data.get('company', 'Employer')} — {job.data.get('title', 'Internship')} closes {deadline.strftime('%d %b %Y, %H:%M UTC')}. {qualification}"
                event(db, user.id, "deadline_reminder", message, notify=True, opportunity_id=job.id)
                sent += 1
                allowance -= 1
                if not allowance:
                    break
        db.commit()
    return sent
