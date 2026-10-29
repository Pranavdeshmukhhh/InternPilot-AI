import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from sqlalchemy import select, func, update, or_
from sqlalchemy.exc import IntegrityError
from .config import settings
from .database import SessionLocal
from .models import User, Source, SourceOpportunity, Opportunity, Application, Document, AuditEvent, Notification, Task, SavedOpportunity, CrawlRun, CatalogSource, CatalogListing, OpportunityArchive, now
from .security import encrypt, decrypt, encrypt_bytes, decrypt_bytes, digest, approval_digest
from . import realtime  # noqa: F401 -- registers post-commit Redis wakeups.

logger = logging.getLogger(__name__)


def timestamp(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def event(db, owner_id, kind, message, application_id=None, notify=False, opportunity_id=None, dedupe_key=None):
    if notify and dedupe_key:
        scoped_key = digest("notification:" + owner_id + ":" + dedupe_key)
        if db.scalar(select(Notification.id).where(Notification.owner_id==owner_id,Notification.dedupe_key.in_((dedupe_key, scoped_key)))):
            return None
        dedupe_key = scoped_key
    message = str(message)[:1500]
    row = AuditEvent(owner_id=owner_id, kind=kind, message=message, application_id=application_id)
    db.add(row)
    db.info.setdefault("realtime_updates",set()).add(owner_id)
    if notify:
        if dedupe_key is None:
            db.add(Notification(owner_id=owner_id, kind=kind, message=message, opportunity_id=opportunity_id))
        else:
            try:
                with db.begin_nested():
                    db.add(Notification(owner_id=owner_id, kind=kind, message=message, opportunity_id=opportunity_id, dedupe_key=dedupe_key))
                    db.flush()
            except IntegrityError:
                pass
    return row


def bulk_notifications(db, rows):
    from uuid import uuid4
    from .catalog import insert_for
    for offset in range(0, len(rows), 200):
        batch = [{**row,"id":str(uuid4()),"read":False,"created_at":now(),"message":str(row["message"])[:1500]} for row in rows[offset:offset + 200]]
        stmt = insert_for(db, Notification.__table__).values(batch)
        inserted = list(db.execute(stmt.on_conflict_do_nothing(index_elements=["dedupe_key"])
            .returning(Notification.owner_id, Notification.kind, Notification.message)))
        if inserted:
            db.execute(AuditEvent.__table__.insert(), [{"owner_id":owner,"kind":kind,"message":message} for owner,kind,message in inserted])
            db.info.setdefault("realtime_updates", set()).update(owner for owner, _, _ in inserted)


def notify_saved_changes(db, messages, owner_id=None):
    """Batched private fan-out for shared fact changes; no recipient info leaks.

    Keys are canonical IDs, values are (kind, text, episode fingerprint).
    Only in-app notifications are created; external delivery approval is unchanged.
    """
    if not messages:
        return
    target = func.coalesce(Opportunity.canonical_id, Opportunity.id)
    ids = list(messages)
    for start in range(0, len(ids), 200):
        query = select(SavedOpportunity.owner_id, SavedOpportunity.opportunity_id, target).join(Opportunity, Opportunity.id == SavedOpportunity.opportunity_id)
        query = query.where(target.in_(ids[start:start + 200]))
        if owner_id:
            query = query.where(SavedOpportunity.owner_id == owner_id)
        recipients = list(db.execute(query))
        for offset in range(0, len(recipients), 200):
            rows = []
            for owner, saved_id, canonical in recipients[offset:offset + 200]:
                kind, message, episode = messages[canonical]
                rows.append({"owner_id":owner, "opportunity_id":saved_id, "kind":kind,
                    "message":message[:1500], "read":False, "created_at":now(),
                    "dedupe_key":digest("notification:" + owner + ":" + episode)})
            bulk_notifications(db, rows)


def visible_jobs(db, user_id):
    from .catalog_query import visible_ids
    ids = visible_ids(user_id)
    return db.scalars(select(Opportunity).where(Opportunity.id.in_(ids))).all()


def job_for_user(db, user_id, job_id):
    # Authorize exactly this ID. A private alias is not authorized merely because
    # another tenant can see its canonical public record.
    from sqlalchemy import exists
    from .catalog_query import visible_ids
    linked = Opportunity.id.in_(visible_ids(user_id))
    saved = or_(Opportunity.id.in_(visible_ids(user_id, saved=True)), exists(select(SavedOpportunity.owner_id).where(SavedOpportunity.owner_id == user_id, SavedOpportunity.opportunity_id == Opportunity.id)))
    applied = exists(select(Application.id).where(Application.owner_id == user_id, Application.opportunity_id == Opportunity.id))
    historical = exists(select(OpportunityArchive.opportunity_id).where(OpportunityArchive.owner_id == user_id, OpportunityArchive.opportunity_id == Opportunity.id))
    return db.scalar(select(Opportunity).where(Opportunity.id == job_id, or_(linked, saved, applied, historical)))


def job_view(job, profile):
    from .opportunity_intelligence import evaluate_opportunity
    from .geography import classify
    from .discovery_filters import disclosed_details
    data = dict(job.data)
    data.setdefault("opportunity_type", "internship")
    result = evaluate_opportunity(data, profile)
    if data.get("active") is False:
        result = {**result,"eligibility":"ineligible","score":0,"reasons":["Listing is no longer present in a complete source response",*result.get("reasons",[])]}
    verified_time = timestamp(job.last_verified)
    if verified_time and verified_time < datetime.now(timezone.utc) - timedelta(days=2) and result["eligibility"] != "ineligible":
        result = {**result, "eligibility":"review", "reasons":[*result.get("reasons", []), "Listing has not been verified in the last 48 hours"]}
    expiry = timestamp(data.get("deadline")) or (timestamp(data.get("ends_at")) if data["opportunity_type"] == "hackathon" else None)
    unknown_registration = data["opportunity_type"]=="hackathon" and data.get("registration_status","unknown")=="unknown"
    status = "expired" if expiry and expiry <= datetime.now(timezone.utc) else "closed" if data.get("active") is False else "unverified" if unknown_registration or data.get("verification_status") in {"unverified", "reference_only"} else "open"
    if status=="unverified" and result["eligibility"]!="ineligible":
        result = {**result,"eligibility":"review","reasons":[*result.get("reasons",[]),"The official application link or current registration availability still needs verification."],"recommended_action":"Verify the official opportunity page and current application or registration availability before proceeding."}
    if status == "expired":
        result = {**result,"eligibility":"ineligible","score":0,"recommended_action":"This opportunity has expired. Keep it for reference."}
    return {**data, "status":status,"id":job.id,"first_discovered":job.first_discovered,"last_verified":job.last_verified,**result,"evaluation":result,"geography":classify(data,profile),"disclosed_details":disclosed_details(data)}


def source_view(row):
    return {key:getattr(row,key) for key in ("id","kind","slug","company","url","permitted","enabled","interval_seconds","last_attempt","last_success","next_run","status","error","failures","discovered_count")} | {"truncated":bool((row.cache or {}).get("truncated"))}


_NOT_LOADED = object()


def application_view(db, row, job=_NOT_LOADED):
    if job is _NOT_LOADED:
        job = db.get(Opportunity, row.opportunity_id)
    upload_supported = bool(not row.is_demo and row.document_id and row.status in {"awaiting_review","needs_input"} and not row.upload_started_at and not row.upload_approved_at)
    upload_status = "uncertain" if row.upload_started_at and row.status == "uncertain" else "needs_input" if row.upload_started_at and row.status == "needs_input" else "prepared" if row.upload_started_at else "approved" if row.upload_approved_at else "awaiting_approval"
    return {key:getattr(row,key) for key in ("id","opportunity_id","status","reason","document_id","screenshot_id","confirmation_id","created_at","updated_at","approved_at","is_demo","preparation_seconds","submission_seconds","upload_approved_at","upload_started_at")} | {"upload_supported":upload_supported,"upload_status":upload_status,"title":job.data.get("title", "Unknown") if job else "Unknown", "company":job.data.get("company", "Unknown") if job else "Unknown", "url":job.data.get("url") if job else None, "submission_supported":bool(row.is_demo and settings.test_mode),"confirmation_text":decrypt(row.confirmation_encrypted).get("text") if row.confirmation_encrypted else None,"fields":decrypt(row.snapshot_encrypted).get("form_fields",[]) if row.snapshot_encrypted else []}


def document_view(row):
    return {key:getattr(row,key) for key in ("id","filename","kind","version","created_at","opportunity_id")}


def enqueue(db, owner_id, kind, payload, dedupe_key, priority=0):
    task = db.scalar(select(Task).where(Task.dedupe_key == dedupe_key).with_for_update())
    if task and task.status in ("queued","running"):
        return task
    from .coordination import admit_task
    admit_task(db, owner_id)
    if task:
        task.status, task.payload, task.error = "queued", payload, None
        task.available_at, task.updated_at = now(), now()
        task.attempts = 0
        task.priority = priority
    else:
        task = Task(owner_id=owner_id,kind=kind,payload=payload,dedupe_key=dedupe_key,priority=priority)
        try:
            with db.begin_nested():
                db.add(task)
                db.flush()
        except IntegrityError:
            task = db.scalar(select(Task).where(Task.dedupe_key==dedupe_key).with_for_update())
            if task is None:
                raise
    db.flush()
    return task


def application_priority(view, at=None):
    """Prefer imminent deadlines, then match score, in the preparation queue."""
    at = at or datetime.now(timezone.utc)
    score = max(0, min(100, int(view.get("score", 0))))
    deadline = timestamp(view.get("deadline"))
    remaining = (deadline - at).total_seconds() if deadline else None
    if remaining is not None and 0 < remaining <= 86400:
        return score + 1000
    if remaining is not None and 0 < remaining <= 3 * 86400:
        return score + 500
    if remaining is not None and 0 < remaining <= 7 * 86400:
        return score + 200
    return score


def automatic_preparation_ready(policy, profile):
    required = {"name", "email", "degree", "university", "skills"}
    return bool(
        policy.get("auto_prepare", False)
        and policy.get("mode") in {"assisted", "auto"}
        and not policy.get("emergency_stop", False)
        and required.issubset(profile.get("verified_fields", []))
        and all(profile.get(field) for field in required)
        and (policy.get("mode") != "auto" or policy.get("auto_consent", False))
    )


def permitted_opportunity_ids(db, owner_id, job_ids):
    """Batch current source authorization; historical links alone are insufficient."""
    from .catalog_migrations import source_key
    sources = list(db.scalars(select(Source).where(Source.owner_id == owner_id, Source.enabled == True,
        Source.permitted == True, Source.kind != "test")))
    if not sources or not job_ids:
        return set()
    disabled = set(db.scalars(select(CatalogSource.id).where(CatalogSource.enabled == False)))
    allowed = {s.id:s for s in sources if source_key({k:getattr(s,k) for k in ("kind", "slug", "company", "url")}) not in disabled}
    if not allowed:
        return set()
    active_sets = {}
    for sid, source in allowed.items():
        cache = source.cache or {}
        active = cache.get("active_opportunity_ids")
        active_sets[sid] = None if "active_opportunity_ids" not in cache else {i for i in active if isinstance(i, str)} if isinstance(active, list) else set()
    result = set()
    ids = list(job_ids)
    for start in range(0, len(ids), 200):
        chunk = ids[start:start + 200]
        links = db.execute(select(SourceOpportunity.source_id, Opportunity.id, Opportunity.canonical_id)
            .join(Opportunity, Opportunity.id == SourceOpportunity.opportunity_id)
            .where(SourceOpportunity.source_id.in_(allowed), or_(Opportunity.id.in_(chunk), Opportunity.canonical_id.in_(chunk))))
        for sid, original, canonical in links:
            active = active_sets[sid]
            if active is None or original in active or canonical in active:
                result.update((original, canonical or original))
    return result


def has_current_permitted_source(db, owner_id, job_id):
    job = job_for_user(db, owner_id, job_id)
    if not job:
        return False
    canonical = job.canonical_id or job.id
    return canonical in permitted_opportunity_ids(db, owner_id, [canonical])


def automatic_opportunity_allowed(db, owner_id, job, view, policy, at, permitted_ids=None):
    """Automatic preparation only uses current, explicitly permitted sources."""
    if job.data.get("opportunity_type", "internship") != "internship" or job.data.get("is_demo") or job.data.get("active") is False or view.get("status")=="unverified" or view["eligibility"] != "eligible":
        return False
    verified = timestamp(job.last_verified)
    deadline = timestamp(job.data.get("deadline"))
    if not verified or verified < at - timedelta(hours=48) or (deadline and deadline <= at):
        return False
    if view["score"] < policy.get("preparation_minimum_score", 70):
        return False
    if not (job.id in permitted_ids if permitted_ids is not None else has_current_permitted_source(db, owner_id, job.id)):
        return False
    if policy.get("mode") == "auto":
        origin = urlsplit(job.data.get("url", ""))
        return bool(
            view["score"] >= policy.get("minimum_score", 80)
            and view.get("company", "").casefold() in {c.casefold() for c in policy.get("allowed_companies", [])}
            and f"{origin.scheme}://{origin.netloc}" in policy.get("allowed_origins", [])
        )
    return True


def queue_automatic_preparation(owner_id=None, at=None):
    """Queue opted-in review packages, with a durable per-owner daily budget.

    Rechecking periodically also handles newly verified profiles and changed
    preferences without another network scan. No submission consent is created.
    """
    at = at or datetime.now(timezone.utc)
    with SessionLocal() as db:
        owners = list(db.scalars(select(User.id).where(User.id == owner_id))) if owner_id else list(db.scalars(select(User.id)))
    queued = 0
    for account_id in owners:
        try:
            with SessionLocal() as db:
                # SQLite ignores FOR UPDATE. This short write transaction provides
                # the same serialization for concurrent local schedulers.
                if db.get_bind().dialect.name == "sqlite":
                    db.execute(update(User).where(User.id == account_id).values(id=User.id))
                user = db.scalar(select(User).where(User.id == account_id).with_for_update())
                if user is None or user.disabled:
                    continue
                policy, profile = decrypt(user.policy_encrypted), decrypt(user.profile_encrypted)
                if not automatic_preparation_ready(policy, profile):
                    continue
                since = at.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
                used = db.scalar(select(func.count()).select_from(Application).where(
                    Application.owner_id == account_id, Application.is_demo == False, Application.created_at >= since))
                remaining = max(0, min(50, int(policy.get("daily_preparation_limit", 10))) - used)
                if not remaining:
                    continue
                histories = list(db.execute(select(Application.opportunity_id, Opportunity.canonical_id, Opportunity.url_key)
                    .join(Opportunity, Opportunity.id == Application.opportunity_id).where(Application.owner_id == account_id)))
                existing = {ident for original, canonical, _ in histories for ident in (original, canonical) if ident}
                existing_urls = {key for _, _, key in histories if key}
                candidates = []
                jobs = visible_jobs(db, account_id)
                permitted = permitted_opportunity_ids(db, account_id, [job.id for job in jobs])
                for job in jobs:
                    if job.id in existing or job.url_key and job.url_key in existing_urls:
                        continue
                    view = job_view(job, profile)
                    if automatic_opportunity_allowed(db, account_id, job, view, policy, at, permitted_ids=permitted):
                        candidates.append((application_priority(view, at), job.id))
                created = 0
                for priority, job_id in sorted(candidates, key=lambda item: (-item[0], item[1])):
                    if created >= remaining:
                        break
                    try:
                        with db.begin_nested():
                            row = Application(owner_id=account_id, opportunity_id=job_id)
                            db.add(row)
                            db.flush()
                            enqueue(db, account_id, "application", {"application_id":row.id, "automatic_preparation":True}, f"application:{row.id}", priority)
                            event(db, account_id, "application_queued", "Automatically queued verified application preparation", row.id)
                    except IntegrityError:
                        continue  # A manual request already created this application.
                    created += 1
                db.commit()
                queued += created
        except Exception as exc:
            # A malformed account must not prevent other owners' automation.
            logger.error("Automatic preparation failed for an account (%s)", type(exc).__name__)
    return queued


def canonical_fingerprint(job):
    parts = urlsplit(job["url"])
    query = urlencode(sorted((k,v) for k,v in parse_qsl(parts.query) if k.lower() not in {"source","ref","gh_src","lever-source"} and not k.lower().startswith("utm_")))
    canonical = urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), query, ""))
    return digest(canonical)


def merge_opportunity_data(previous, incoming):
    """References must not overwrite richer independently verified ATS facts."""
    reference_sources = {"internscan", "jobspy_feed", "jobspy", "github_list", "search"}
    reference_statuses = {"unverified", "reference_only"}
    previous_rich = (previous.get("source") not in reference_sources and previous.get("verification_status") not in reference_statuses) or previous.get("verification_status")=="official_metadata_verified"
    incoming_reference = incoming.get("source") in reference_sources or incoming.get("verification_status") in reference_statuses
    weaker = incoming_reference and previous_rich and previous.get("verification_status") not in reference_statuses and (incoming.get("verification_status")!="official_metadata_verified" or previous.get("source") not in reference_sources)
    if weaker:
        merged = dict(previous)
        merged["discovered_via"] = sorted(set(previous.get("discovered_via",[])) | {incoming.get("source")})
        return merged,False
    merged = dict(incoming)
    for field in ("published_at","published_date","source_created_at"):
        if not merged.get(field) and previous.get(field):
            merged[field] = previous[field]
    return merged,True


def store_document(db, owner_id, output, kind, opportunity_id=None):
    version = (db.scalar(select(func.max(Document.version)).where(Document.owner_id==owner_id, Document.kind==kind, Document.opportunity_id==opportunity_id)) or 0) + 1
    row = Document(owner_id=owner_id,opportunity_id=opportunity_id,filename=output["filename"],kind=kind,version=version,content_encrypted=encrypt_bytes(output["content"]),metadata_encrypted=encrypt({k:v for k,v in output.items() if k not in ("content","filename")}))
    db.add(row)
    db.flush()
    return row


async def process_discovery(owner_id, source_id=None, *, task_id=None, lease_owner=None, task_attempt=None):
    from .discovery import discover
    with SessionLocal() as db:
        user = db.get(User, owner_id)
        if user is None or user.disabled or decrypt(user.policy_encrypted).get("emergency_stop", False):
            return
        query = select(Source).where(Source.owner_id==owner_id,Source.enabled==True,Source.permitted==True)
        if source_id:
            query = query.where(Source.id==source_id)
        source_ids = [s.id for s in db.scalars(query)]
    semaphore = asyncio.Semaphore(3)
    touched_ids = set()

    async def scan(sid):
        async with semaphore:
            with SessionLocal() as db:
                if not valid_lease(db, task_id, lease_owner):
                    return
                if task_id and db.get(Task, task_id).attempts != task_attempt:
                    return
                source = db.scalar(select(Source).where(Source.id == sid).with_for_update())
                user = db.get(User, owner_id)
                # A queued scan may outlive a stop, source deletion, permission
                # change, or a previous scan's server-imposed retry delay.
                if (source is None or user is None or user.disabled or source.owner_id != owner_id
                        or not source.enabled or not source.permitted
                        or decrypt(user.policy_encrypted).get("emergency_stop", False)
                        or (source.failures and source.next_run and source.next_run > now())):
                    return
                source.last_attempt, source.status = now(), "running"
                source.scan_generation = (source.scan_generation or 0) + 1
                generation = source.scan_generation
                crawl = CrawlRun(owner_id=owner_id,source_id=sid)
                db.add(crawl);db.flush()
                run_id,scan_started = crawl.id,time.monotonic()
                source_data, cache = source_view(source), source.cache
                from .catalog import reviewed_source, claim_public_scan, cached_public_result
                registry = reviewed_source(db, source)
                public_id, token, shared_result = None, None, None
                if registry:
                    mode, registry, token = claim_public_scan(db, registry, source.interval_seconds)
                    public_id = registry.id
                    if mode in {"busy", "paused", "backoff"}:
                        crawl.finished_at, crawl.outcome = now(), "deferred"
                        source.status = "paused" if mode == "paused" else "waiting"
                        from .models import DiscoveryHealth
                        health = db.get(DiscoveryHealth, registry.id)
                        if health and health.next_attempt:
                            source.next_run = health.next_attempt
                        else:
                            source.next_run = registry.lease_until if mode == "busy" else (datetime.now(timezone.utc) + timedelta(seconds=900)).isoformat()
                        db.commit()
                        return
                    if mode == "cached":
                        if (source.cache or {}).get("catalog_generation") == registry.generation and (source.cache or {}).get("profile_signature") == digest(user.profile_encrypted.hex()):
                            crawl.finished_at, crawl.outcome, crawl.records = now(), "cached", source.discovered_count
                            source.status = "partial" if (registry.cache or {}).get("truncated") else "reference" if (registry.cache or {}).get("reference_feed") else "healthy"
                            source.last_success, source.failures = registry.last_success, 0
                            if source.status == "healthy":
                                source.error = None
                            source.next_run = (datetime.now(timezone.utc) + timedelta(seconds=source.interval_seconds)).isoformat()
                            db.commit()
                            return
                        shared_result = cached_public_result(db, registry)
                    cache = registry.cache
                db.commit()
            try:
                discovery_input = {**source_data, "company":registry.config["company"], "url":registry.config.get("url")} if public_id else source_data
                from .models import DiscoveryHealth
                health_key = public_id or sid
                with SessionLocal() as db:
                    health = db.get(DiscoveryHealth, health_key)
                    discovery_input["_pagination_checkpoint"] = health.checkpoint if health else {}
                async def save_checkpoint(progress):
                    def persist():
                        with SessionLocal() as db:
                            if not valid_lease(db, task_id, lease_owner):
                                return
                            current = db.scalar(select(Source).where(Source.id == sid).with_for_update())
                            if not current or current.scan_generation != generation:
                                return
                            if public_id:
                                publisher = db.scalar(select(CatalogSource).where(CatalogSource.id == public_id).with_for_update())
                                if publisher.lease_token != token or not publisher.lease_until or publisher.lease_until <= now():
                                    return
                            from .catalog import insert_for
                            stmt = insert_for(db, DiscoveryHealth.__table__).values(key=health_key, checkpoint=progress, failures=0)
                            db.execute(stmt.on_conflict_do_update(index_elements=["key"],set_={"checkpoint":progress}))
                            db.commit()
                    await asyncio.to_thread(persist)
                discovery_input["_save_checkpoint"] = save_checkpoint
                async with asyncio.timeout(120):
                    result = shared_result if shared_result is not None else await discover(discovery_input, cache=cache)
                if public_id and result.get("not_modified"):
                    with SessionLocal() as db:
                        registry = db.get(CatalogSource, public_id)
                        snapshot = cached_public_result(db, registry)
                    result = {**result, "jobs":snapshot["jobs"], "shared_verified_at":now()}
                from .llm import annotate_jobs
                with SessionLocal() as db:
                    urls = [str(item.get("url")) for item in result["jobs"] if item.get("url")]
                    matching = db.scalars(select(Opportunity).join(SourceOpportunity,SourceOpportunity.opportunity_id==Opportunity.id).join(Source,Source.id==SourceOpportunity.source_id).where(Source.owner_id==owner_id,Opportunity.data["url"].as_string().in_(urls))).unique() if urls else []
                    previous = {j.data.get("url"):j.data for j in matching}
                    account = db.get(User,owner_id)
                    candidate_profile = decrypt(account.profile_encrypted)
                # Shared extraction must never depend on one subscriber's profile.
                if shared_result is None:
                    from .coordination import reserve_inference
                    limit = settings.llm_scan_job_limit
                    try:
                        async with asyncio.timeout(30):
                            result["jobs"] = await annotate_jobs(result["jobs"][:limit],previous_by_url=previous,profile=None if public_id else candidate_profile, reserve_budget=reserve_inference) + result["jobs"][limit:]
                    except TimeoutError:
                        logger.warning("Discovery enrichment deadline reached; preserving deterministic facts")
                added = 0
                with SessionLocal() as db:
                    if not valid_lease(db, task_id, lease_owner):
                        return
                    if task_id and db.get(Task, task_id).attempts != task_attempt:
                        return
                    # Serialize cache updates with source-review dismissals.
                    source = db.scalar(select(Source).where(Source.id==sid).with_for_update())
                    if source is None or not source.enabled or not source.permitted or source.scan_generation != generation:
                        return
                    account = db.get(User, owner_id)
                    if account is None or account.disabled or decrypt(account.policy_encrypted).get("emergency_stop", False):
                        return
                    # Source edits while the request runs invalidate its result.
                    if any(getattr(source, key) != source_data[key] for key in ("kind", "slug", "company", "url")):
                        return
                    registry = db.scalar(select(CatalogSource).where(CatalogSource.id == public_id).with_for_update()) if public_id else None
                    if public_id and (registry is None or not registry.enabled or (token and (registry.lease_token != token or timestamp(registry.lease_until) <= datetime.now(timezone.utc)))):
                        return
                    if registry and shared_result is not None:
                        result = cached_public_result(db, registry)
                    crawl = db.get(CrawlRun,run_id)
                    crawl.finished_at,crawl.seconds,crawl.records,crawl.outcome = now(),round(time.monotonic()-scan_started,3),len(result["jobs"]),"cached" if result.get("not_modified") else "success"
                    linked_jobs = list(db.scalars(select(Opportunity).join(SourceOpportunity,SourceOpportunity.opportunity_id==Opportunity.id).where(SourceOpportunity.source_id==sid)))
                    active_ids = set((source.cache or {}).get("active_opportunity_ids",[j.id for j in linked_jobs if j.data.get("active") is not False]))
                    verified_ids = set((source.cache or {}).get("verified_opportunity_ids",active_ids))
                    if result.get("not_modified"):
                        if registry:
                            verified = select(CatalogListing.opportunity_id).where(CatalogListing.source_id == registry.id, CatalogListing.active == True, CatalogListing.verified == True)
                            db.execute(update(Opportunity).where(Opportunity.id.in_(verified)).values(last_verified=now()))
                        for verified_job in linked_jobs:
                            reference = source.kind in {"internscan","jobspy_feed","github_list","search"}
                            evidence = verified_job.data.get("verification_evidence_url")
                            same_publisher_page = source.kind != "html" or bool(evidence and evidence == (source.cache or {}).get("publisher_url"))
                            authoritative = source.kind!="search" and same_publisher_page and verified_job.data.get("verification_status") not in {"reference_only", "unverified"} and (not reference or verified_job.data.get("source") == source.kind)
                            if authoritative and verified_job.id in verified_ids and verified_job.data.get("active") is not False:
                                verified_job.last_verified = now()
                    seen_ids = set()
                    verified_seen_ids = set()
                    from .catalog import ingest, insert_for
                    jobs, added, changes, aliases = ingest(db, owner_id, source, result["jobs"], public=bool(registry),
                        verified_at=result.get("shared_verified_at"), link_only=shared_result is not None or bool(registry and result.get("not_modified")))
                    active_ids = {aliases.get(i, i) for i in active_ids}
                    linked_jobs = [j for j in linked_jobs if j.id not in aliases]
                    seen_ids = {j.id for j in jobs}
                    verified_seen_ids = {j.id for j in jobs if j.data.get("verification_status") not in {"unverified", "reference_only"}}
                    if registry and result.get("not_modified"):
                        active_ids |= seen_ids
                        verified_ids |= verified_seen_ids
                    changed_messages = {}
                    for ident, before, after, fields in changes:
                        key = digest(json.dumps({"job":ident,"before":{k:before.get(k) for k in fields},"after":{k:after.get(k) for k in fields}}, sort_keys=True, default=str))
                        changed_messages[ident] = ("saved_opportunity_changed", f"{after.get('company','Employer')} — {after.get('title','Opportunity')}: updated {', '.join(fields)}. Review the latest source information.", "changed:" + key)
                    notify_saved_changes(db, changed_messages, owner_id=None if registry else owner_id)
                    if registry and token and not result.get("not_modified"):
                        memberships = [{"source_id":registry.id, "opportunity_id":j.id, "active":True, "verified":j.id in verified_seen_ids} for j in jobs]
                        for start in range(0, len(memberships), 200):
                            stmt = insert_for(db, CatalogListing.__table__).values(memberships[start:start + 200])
                            db.execute(stmt.on_conflict_do_update(index_elements=["source_id", "opportunity_id"], set_={"active":stmt.excluded.active, "verified":stmt.excluded.verified}))
                        if not result.get("cache", {}).get("truncated"):
                            db.execute(update(CatalogListing).where(CatalogListing.source_id == registry.id, CatalogListing.opportunity_id.not_in(seen_ids)).values(active=False))
                    closed_messages = {}
                    if not result.get("not_modified"):
                        if result.get("cache",{}).get("truncated"):
                            active_ids |= seen_ids
                        else:
                            active_ids = seen_ids
                            other_sources = list(db.scalars(select(Source).where(Source.owner_id==owner_id,Source.id!=sid))) if not registry else []
                            source_ids = select(SourceOpportunity.opportunity_id).where(SourceOpportunity.source_id == sid)
                            public_active = set(db.scalars(select(CatalogListing.opportunity_id).where(CatalogListing.active == True, CatalogListing.verified == True, CatalogListing.opportunity_id.in_(source_ids)))) if registry else set()
                            all_active, official_active = set(), set()
                            for other in other_sources:
                                if other.enabled and other.permitted:
                                    all_active.update((other.cache or {}).get("active_opportunity_ids", []))
                                    if other.kind not in {"internscan","jobspy_feed","github_list","search"}:
                                        official_active.update((other.cache or {}).get("active_opportunity_ids", []))
                            for missing in linked_jobs:
                                if missing.id in seen_ids:
                                    continue
                                reference_kinds = {"internscan","jobspy_feed","github_list","search"}
                                official_data = missing.data.get("source") not in reference_kinds
                                still_available = missing.id in (public_active if registry else official_active if official_data else all_active)
                                if missing.catalog_scope == "public" and not registry:
                                    still_available = True  # Private subscriptions cannot close public facts.
                                if not still_available:
                                    missing.data = {**missing.data,"active":False,"closing_evidence":{"reason":"absent_from_complete_inventory", "checked_at":now(),"source_id":public_id or sid}}
                                    closed_messages[missing.id] = ("saved_opportunity_closed", f"{missing.data.get('company','Employer')} — {missing.data.get('title','Opportunity')} is no longer listed by the verified source.", "closed:" + digest(missing.id + str(missing.last_verified)))
                    notify_saved_changes(db, closed_messages, owner_id=None if registry else owner_id)
                    next_cache = dict(result.get("cache", {}))
                    if registry:
                        if token:
                            registry.cache, registry.last_success = next_cache, now()
                            registry.lease_token, registry.lease_until = None, None
                            registry.generation += 1
                            from .coordination import health_success
                            health_success(db, registry.id)
                        # Large detail caches are stored once, not per subscriber.
                        next_cache = {k:v for k,v in next_cache.items() if k != "details"}
                        next_cache.update(catalog_source_id=registry.id, catalog_generation=registry.generation,
                            profile_signature=digest(account.profile_encrypted.hex()))
                    if source.kind in {"search", "html"}:
                        from .publisher_discovery import merge_candidates
                        next_cache["source_candidates"] = merge_candidates((source.cache or {}).get("source_candidates", []), next_cache.get("source_candidates", []))
                    # A review/dismissal can happen while a network scan runs.
                    # Preserve the latest user decision instead of scan-start state.
                    next_cache["dismissed_source_candidate_ids"] = (source.cache or {}).get("dismissed_source_candidate_ids", [])[-500:]
                    source.cache = {**next_cache,"active_opportunity_ids":sorted(active_ids),"verified_opportunity_ids":sorted(verified_ids if result.get("not_modified") else verified_seen_ids)}
                    checkpoint_row = db.get(DiscoveryHealth, health_key)
                    if checkpoint_row and checkpoint_row.checkpoint.get("pending_rows"):
                        checkpoint_row.checkpoint = {k:v for k,v in checkpoint_row.checkpoint.items() if k != "pending_rows"}
                    touched_ids.update(active_ids if result.get("not_modified") else seen_ids)
                    source.status, source.error, source.failures = "healthy", None, 0
                    if result.get("cache", {}).get("reference_feed"):
                        source.status = "reference"
                    elif result.get("cache", {}).get("truncated"):
                        note = "Search references do not establish a complete inventory; publisher verification is bounded" if source.kind == "search" else "Publisher page scan is bounded; linked opportunities may require review" if source.kind == "html" else "Connector page limit reached; some postings may not have been scanned"
                        source.status, source.error = "partial", note
                    source.last_success, source.discovered_count = registry.last_success if registry else now(), len(result["jobs"]) if not result.get("not_modified") else source.discovered_count
                    source.next_run = (datetime.now(timezone.utc)+timedelta(seconds=max(source.interval_seconds, int(next_cache.get("pagination_retry_after", 0))))).isoformat()
                    evidence = "reference feed" if source.status=="reference" else "source scan completed"
                    event(db,owner_id,"discovery",f"{source.company}: {evidence}; {added} new opportunities",notify=added>0)
                    db.commit()
            except Exception as exc:
                with SessionLocal() as db:
                    if not valid_lease(db, task_id, lease_owner):
                        return
                    if task_id and db.get(Task, task_id).attempts != task_attempt:
                        return
                    if public_id and token:
                        released = db.execute(update(CatalogSource).where(CatalogSource.id == public_id, CatalogSource.lease_token == token)
                            .values(lease_token=None, lease_until=None))
                        if not released.rowcount:
                            return
                    source = db.get(Source,sid)
                    if source is None:
                        return
                    if source.scan_generation != generation:
                        return
                    source.failures += 1
                    crawl = db.get(CrawlRun,run_id)
                    if crawl:
                        crawl.finished_at,crawl.seconds,crawl.outcome = now(),round(time.monotonic()-scan_started,3),"error"
                    # Avoid leaking credentials/query strings from network exception representations.
                    source.error = f"{type(exc).__name__}: source scan failed; check source permissions and configuration"
                    source.status = "error"
                    backoff = min(86400, source.interval_seconds * 2**min(source.failures,5))
                    from .coordination import health_failure, retry_delay
                    if public_id and token:
                        health_failure(db, public_id, exc, source.interval_seconds)
                    backoff = retry_delay(source.failures, base=source.interval_seconds)
                    retry_after = max(0, int(getattr(exc,"retry_after",0) or 0))
                    source.next_run = (datetime.now(timezone.utc)+timedelta(seconds=max(backoff,retry_after))).isoformat()
                    event(db,owner_id,"discovery_error",f"{source.company}: discovery failed ({type(exc).__name__})",notify=True)
                    db.commit()
    work = asyncio.Queue(maxsize=16)
    async def consume():
        while True:
            sid = await work.get()
            try:
                if sid is None:
                    return
                await scan(sid)
            finally:
                work.task_done()
    consumers = [asyncio.create_task(consume()) for _ in range(min(3, len(source_ids)))]
    async def produce():
        for sid in source_ids:
            await work.put(sid)
        for _ in consumers:
            await work.put(None)
    producer = asyncio.create_task(produce())
    try:
        await asyncio.gather(producer, *consumers)
    finally:
        producer.cancel()
        await asyncio.gather(producer, return_exceptions=True)
        for consumer in consumers:
            consumer.cancel()
        await asyncio.gather(*consumers, return_exceptions=True)
    with SessionLocal() as db:
        user = db.get(User,owner_id)
        if user:
            policy,profile = decrypt(user.policy_encrypted),decrypt(user.profile_encrypted)
            if policy.get("new_match_alerts",True):
                already = set()
                touched = list(touched_ids)
                canonical = func.coalesce(Opportunity.canonical_id, Opportunity.id)
                for start in range(0, len(touched), 200):
                    already.update(db.scalars(select(canonical).join(Notification, Notification.opportunity_id == Opportunity.id)
                        .where(Notification.owner_id == owner_id, Notification.kind == "high_match", canonical.in_(touched[start:start + 200]))))
                notifications = []
                for job in db.scalars(select(Opportunity).where(Opportunity.id.in_(touched_ids))):
                    if job.id in already:
                        continue
                    view = job_view(job,profile)
                    if view["eligibility"]!="ineligible" and view["status"] not in {"expired","closed"} and view["score"]>=policy.get("alert_minimum_score",70):
                        notifications.append({"owner_id":owner_id,"kind":"high_match", "message":f"{view['company']} — {view['title']} matches {view['score']}/100. {view['recommended_action']}",
                            "opportunity_id":job.id,"dedupe_key":digest("notification:" + owner_id + ":match:" + job.id)})
                bulk_notifications(db, notifications)
            db.commit()
    queue_automatic_preparation(owner_id)


DEMO_PROFILE = {"name":"InternPilot Test Candidate","email":"candidate@example.test","country":"India","graduation_year":2029,"degree":"Bachelor of Technology","university":"Authorized Test University","skills":["Python","TypeScript"],"projects":[{"name":"Test project","description":"Local application workflow fixture","skills":["Python"]}],"verified_fields":["name","email","country","graduation_year","degree","university","skills","projects"]}


def demo_profile(owner_id):
    # Keep synthetic identities separate across accounts sharing one test portal.
    return {**DEMO_PROFILE,"email":f"candidate+{owner_id}@example.test"}


def seed_demo(db, owner_id):
    url = settings.test_portal_origin+"/test-portal/apply"
    data = {"external_id":"internpilot-local-demo","title":"Software Engineering Intern — LOCAL TEST","company":"InternPilot Test Employer","location":"India / Remote","remote":True,"url":url,"description":"Authorized local test fixture. Undergraduate students graduating in 2029. Python and TypeScript. No real application is sent.","skills":["Python","TypeScript"],"requirements":{"graduation_years":[2029]},"published_at":None,"deadline":None,"compensation":None,"is_demo":True,"source":"local_test"}
    source = db.scalar(select(Source).where(Source.owner_id==owner_id, Source.kind=="test"))
    if source is None:
        source = Source(owner_id=owner_id,kind="test",slug="local",company="LOCAL TEST",enabled=False,permitted=True,status="test")
        db.add(source)
        db.flush()
    fingerprint = digest(owner_id+":"+canonical_fingerprint(data))
    job = db.scalar(select(Opportunity).where(Opportunity.fingerprint==fingerprint))
    if job is None:
        job = Opportunity(fingerprint=fingerprint,data=data)
        db.add(job)
        db.flush()
    if not db.get(SourceOpportunity,(source.id,job.id)):
        db.add(SourceOpportunity(source_id=source.id,opportunity_id=job.id))
    return job


async def process_application(application_id, task_id=None, lease_owner=None, automatic=False):
    from .automation import run_application
    from .documents import generate_resume
    started = time.monotonic()
    with SessionLocal() as db:
        row = db.get(Application,application_id)
        if not row or row.status not in ("queued", "approved", "preparing"):
            return
        if not valid_lease(db,task_id,lease_owner):
            return
        user, job = db.get(User,row.owner_id), db.get(Opportunity,row.opportunity_id)
        profile, policy = decrypt(user.profile_encrypted), decrypt(user.policy_encrypted)
        if user.disabled or policy["emergency_stop"]:
            row.status, row.reason = "needs_input", "Emergency stop is active"
            db.commit()
            return
        demo = row.is_demo and settings.test_mode and job.data.get("is_demo") is True
        if demo:
            profile = demo_profile(row.owner_id)
        view = job_view(job,profile)
        if automatic and (not automatic_preparation_ready(policy, profile) or not automatic_opportunity_allowed(db, row.owner_id, job, view, policy, datetime.now(timezone.utc))):
            row.status, row.reason, row.updated_at = "needs_input", "Automatic preparation paused: verify your profile, source permissions, and preparation policy", now()
            event(db, row.owner_id, "needs_input", row.reason, row.id, notify=True)
            db.commit()
            return
        if not demo and (view["eligibility"]=="ineligible" or policy["mode"]=="discovery"):
            row.status, row.reason = "needs_input", "Opportunity is ineligible or Discovery mode is active"
            db.commit()
            return
        row.status, row.reason, row.updated_at = "preparing", "Preparing verified facts and documents", now()
        previous_snapshot = decrypt(row.snapshot_encrypted) if row.snapshot_encrypted else None
        if previous_snapshot and (previous_snapshot.get("profile")!=profile or previous_snapshot.get("job")!=job.data):
            if row.upload_started_at:
                row.status,row.reason,row.updated_at = "uncertain","Candidate facts changed after a document upload began; review the official application before further action",now()
                db.commit()
                return
            row.document_id,row.approved_at,row.approval_digest = None,None,None
            row.upload_approved_at,row.upload_approval_digest = None,None
        row.snapshot_encrypted = encrypt({"profile":profile,"job":job.data,"policy":policy})
        if row.document_id is None:
            try:
                generated = generate_resume(profile,job.data)
                row.document_id = store_document(db,row.owner_id,generated,"resume",job.id).id
            except ValueError as exc:
                row.status, row.reason = "needs_input", str(exc)[:500]
                event(db,row.owner_id,"needs_input",row.reason,row.id,notify=True)
                db.commit()
                return
        snapshot_digest = approval_digest(profile,job.data,row.document_id)
        upload_approved = bool(row.upload_approved_at and row.upload_approval_digest==snapshot_digest)
        if not demo and row.upload_started_at:
            row.status,row.reason,row.updated_at = "uncertain","An earlier upload may have occurred; reconcile it on the official page before any further upload",now()
            db.commit()
            return
        if not demo and (automatic or not upload_approved):
            # Automatic consent covers drafting only. Visiting an application
            # form or uploading a personal document needs specific approval.
            row.status = "awaiting_review"
            row.reason = "Factual draft prepared. Review it before approving any external action or document upload."
            row.preparation_seconds, row.updated_at = round(time.monotonic()-started, 3), now()
            event(db, row.owner_id, "awaiting_review", row.reason, row.id, notify=True)
            db.commit()
            return
        document = db.get(Document,row.document_id)
        resume = decrypt_bytes(document.content_encrypted)
        approved = bool(row.approved_at and row.approval_digest==snapshot_digest)
        # The local test portal is the only currently certified submission adapter.
        # External opportunities always prepare an assisted review package.
        should_submit = demo
        allowed_origins = [settings.test_portal_origin] if demo else policy["allowed_origins"]
        if approved and not allowed_origins:
            origin = urlsplit(job.data["url"])
            allowed_origins = [f"{origin.scheme}://{origin.netloc}"]
        if not allowed_origins:
            origin = urlsplit(job.data["url"])
            allowed_origins = [f"{origin.scheme}://{origin.netloc}"]
        session_state = decrypt(row.session_encrypted) if row.session_encrypted else None
        owner_id, job_data, doc_id = row.owner_id, dict(job.data), row.document_id
        db.commit()

    async def before_upload():
        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.id==owner_id).with_for_update())
            current = db.get(Application,application_id)
            current_job = db.get(Opportunity,current.opportunity_id)
            current_policy,current_profile = decrypt(user.policy_encrypted),decrypt(user.profile_encrypted)
            expected = approval_digest(current_profile,current_job.data,current.document_id)
            if not valid_lease(db,task_id,lease_owner):
                raise ValueError("Worker lease expired; upload is forbidden")
            if current_policy.get("emergency_stop") or current_policy.get("mode")=="discovery":
                raise ValueError("Application preparation is paused")
            if current.upload_started_at or not current.upload_approved_at or current.upload_approval_digest!=expected or expected!=snapshot_digest:
                raise ValueError("The specific resume upload needs fresh approval")
            if job_view(current_job,current_profile)["eligibility"]=="ineligible":
                raise ValueError("Eligibility changed; upload is forbidden")
            current.upload_started_at,current.updated_at = now(),now()
            event(db,owner_id,"upload_started","Approved document upload checkpoint persisted before browser file assignment",current.id)
            db.commit()
        return True

    async def before_submit(screenshot=None):
        with SessionLocal() as db:
            # Serialize per-user daily submission budget and immediate stop check.
            user = db.scalar(select(User).where(User.id==owner_id).with_for_update())
            current = db.get(Application,application_id)
            if not valid_lease(db,task_id,lease_owner):
                raise ValueError("Worker lease expired; submission is forbidden")
            current_policy = decrypt(user.policy_encrypted)
            current_profile = demo_profile(owner_id) if demo else decrypt(user.profile_encrypted)
            current_job = db.get(Opportunity,current.opportunity_id)
            if current_policy["emergency_stop"]:
                raise ValueError("Emergency stop is active")
            if not screenshot:
                raise ValueError("A durable pre-submission screenshot is required")
            if approval_digest(current_profile,current_job.data,doc_id)!=snapshot_digest:
                raise ValueError("Profile or listing changed; prepare and approve again")
            current_view = job_view(current_job,current_profile)
            if not demo:
                if current_view["eligibility"]!="eligible":
                    raise ValueError("Eligibility is not fully verified")
                current_approved = bool(current.approved_at and current.approval_digest==snapshot_digest)
                current_auto = current_policy["mode"]=="auto" and current_policy["auto_consent"] and current_view["score"]>=current_policy["minimum_score"] and current_job.data.get("company", "").casefold() in {c.casefold() for c in current_policy["allowed_companies"]}
                if current_policy["mode"]=="discovery" or not (current_approved or current_auto):
                    raise ValueError("Explicit submission consent is required")
                parts = urlsplit(current_job.data["url"])
                if current_auto and f"{parts.scheme}://{parts.netloc}" not in current_policy["allowed_origins"]:
                    raise ValueError("Application origin is outside the approved policy")
                since = datetime.now(timezone.utc).date().isoformat()
                used = db.scalar(select(func.count()).select_from(Application).where(Application.owner_id==owner_id,Application.is_demo==False,Application.submission_started_at>=since))
                if used>=current_policy["daily_limit"]:
                    raise ValueError("Daily application limit reached")
            if current.submission_started_at:
                raise ValueError("Submission has already started; reconciliation required")
            shot = store_document(db,owner_id,{"content":screenshot,"filename":"before-submission.png"},"screenshot",current.opportunity_id)
            current.screenshot_id, current.status = shot.id, "submitting"
            current.submission_started_at, current.updated_at = now(), now()
            event(db,owner_id,"submission_started","Persisted screenshot and final policy checks",current.id)
            db.commit()

    try:
        result = await run_application(url=job_data["url"],profile=profile,resume=resume,submit=should_submit,approved=should_submit,allowed_origins=allowed_origins,test_mode=demo,before_submit=before_submit,session_state=session_state,before_upload=before_upload if not demo else None)
        with SessionLocal() as db:
            current = db.get(Application,application_id)
            if not valid_lease(db,task_id,lease_owner) or current.confirmation_id:
                return
            status = result.get("status", "needs_input")
            if status=="submitted" and not (result.get("confirmation_id") and result.get("confirmation_text") and current.submission_started_at):
                status = "uncertain"
            if current.submission_started_at and status not in ("submitted","uncertain"):
                status = "uncertain"
            current.status, current.reason, current.updated_at = status, result.get("reason",status)[:1000], now()
            snapshot = decrypt(current.snapshot_encrypted) if current.snapshot_encrypted else {}
            snapshot["form_fields"] = result.get("fields",[])
            current.snapshot_encrypted = encrypt(snapshot)
            if result.get("screenshot") and not current.screenshot_id:
                current.screenshot_id = store_document(db,owner_id,{"content":result["screenshot"],"filename":"prepared-application.png"},"screenshot",current.opportunity_id).id
            if result.get("session_state"):
                current.session_encrypted = encrypt(result["session_state"])
            if status=="submitted":
                current.confirmation_id = str(result["confirmation_id"])[:200]
                current.confirmation_encrypted = encrypt({"text":result["confirmation_text"]})
            elapsed = round(time.monotonic()-started,3)
            if current.submission_started_at:
                current.submission_seconds = max(0,(datetime.now(timezone.utc)-timestamp(current.submission_started_at)).total_seconds())
                current.preparation_seconds = max(0,elapsed-current.submission_seconds)
            else:
                current.preparation_seconds = elapsed
            event(db,owner_id,status,("LOCAL TEST: " if demo else "")+current.reason,current.id,notify=True)
            db.commit()
    except Exception as exc:
        with SessionLocal() as db:
            current = db.get(Application,application_id)
            if not valid_lease(db,task_id,lease_owner) or current.confirmation_id:
                return
            current.status = "uncertain" if current.submission_started_at or current.upload_started_at else "needs_input"
            current.reason = ("Submission outcome needs reconciliation; automatic retries are disabled" if current.submission_started_at else "Upload outcome needs reconciliation; automatic retries are disabled" if current.upload_started_at else f"Preparation paused ({type(exc).__name__}); check verified profile and application requirements")
            current.updated_at = now()
            event(db,owner_id,current.status,current.reason,current.id,notify=True)
            db.commit()


from contextvars import ContextVar

execution_attempt = ContextVar("execution_attempt", default=None)


def valid_lease(db,task_id,lease_owner):
    if task_id is None:
        return True  # Direct invocation is used only by isolated acceptance tests.
    task = db.scalar(select(Task).where(Task.id==task_id).with_for_update())
    at = db.scalar(select(func.clock_timestamp())).isoformat() if db.get_bind().dialect.name == "postgresql" else now()
    return bool(task and (execution_attempt.get() is None or task.attempts == execution_attempt.get()) and task.status=="running" and task.lease_owner==lease_owner and task.lease_until and timestamp(task.lease_until)>timestamp(at))
