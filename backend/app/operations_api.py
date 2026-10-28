"""Measured operations and bounded, idempotent source provisioning."""
import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .discovery import canonical_url, validate_public_url, _syntax_url
from .models import CrawlRun, Source, Task
from .monitoring import worker_status
from .schemas import SourceInput, StrictModel
from .services import event, source_view


class SourceBatch(StrictModel):
    sources: list[SourceInput] = Field(min_length=1,max_length=1000)


class CandidateApproval(StrictModel):
    permitted: Literal[True]


def candidate_key(source):
    kind, slug, url = source["kind"], source.get("slug", ""), source.get("url") or ""
    return kind, slug, canonical_url(url) if url else ""


def candidate_rows(db, owner_id):
    """Only persisted discoveries belonging to this account are reviewable."""
    sources = list(db.scalars(select(Source).where(Source.owner_id == owner_id).limit(2000)))
    installed = {candidate_key({"kind": row.kind, "slug": row.slug, "url": row.url}) for row in sources}
    dismissed = {value for row in sources for value in (row.cache or {}).get("dismissed_source_candidate_ids", [])[:500] if isinstance(value, str)}
    candidates = {}
    for row in sources:
        for raw in (row.cache or {}).get("source_candidates", [])[:40]:
            if not isinstance(raw, dict):
                continue
            try:
                data = SourceInput(kind=raw["kind"], slug=raw.get("slug", ""), url=raw.get("url"), company=raw["company"], enabled=True, permitted=False, interval_seconds=21600)
                if data.kind not in {"greenhouse", "lever", "ashby", "smartrecruiters", "html", "feed", "workday"}:
                    continue
                key = candidate_key(data.model_dump())
                ident = hashlib.sha256(":".join(key).encode()).hexdigest()[:24]
                evidence = raw.get("evidence_url")
                if not isinstance(evidence, str) or len(evidence) > 1500:
                    continue
                _syntax_url(evidence)
                if data.url:
                    _syntax_url(data.url)
                if ident != raw.get("id") or ident in dismissed or key in installed:
                    continue
            except (ValueError, KeyError, TypeError):
                continue
            candidates.setdefault(ident, {"id": ident, "kind": data.kind, "slug": data.slug, "url": data.url,
                "company": data.company, "evidence_url": evidence, "discovered_at": str(raw.get("discovered_at") or "")[:40],
                "reason": str(raw.get("reason") or "Discovered public source link; access and identity need review.")[:500],
                "verified": False})
    return candidates


def create_router(current_user,require_locked_session):
    router = APIRouter(prefix="/api",tags=["Operations"])

    @router.get("/discovery/source-candidates")
    def source_candidates(user=Depends(current_user), db: Session=Depends(get_db)):
        rows = list(candidate_rows(db, user.id).values())
        rows.sort(key=lambda item: (item["discovered_at"], item["id"]), reverse=True)
        return {"items": rows[:100], "total": len(rows), "note": "Discovered links are unverified source suggestions, not confirmed opportunities. Review the publisher and permitted access before enabling."}

    @router.post("/discovery/source-candidates/{candidate_id}/install")
    async def install_candidate(candidate_id: str, data: CandidateApproval, request: Request, user=Depends(current_user), db: Session=Depends(get_db)):
        candidate = candidate_rows(db, user.id).get(candidate_id)
        if not candidate:
            # Repeated approval returns the already installed source, without
            # granting new permissions or changing its current settings.
            for row in db.scalars(select(Source).where(Source.owner_id == user.id).limit(2000)):
                key = candidate_key({"kind": row.kind, "slug": row.slug, "url": row.url})
                if hashlib.sha256(":".join(key).encode()).hexdigest()[:24] == candidate_id:
                    return source_view(row)
            raise HTTPException(404, "Source suggestion not found")
        try:
            await validate_public_url(candidate["evidence_url"])
            if candidate.get("url"):
                await validate_public_url(candidate["url"])
        except ValueError:
            raise HTTPException(422, "The suggested source is not a permitted public destination") from None
        require_locked_session(request, user, db)
        owned = list(db.scalars(select(Source).where(Source.owner_id == user.id)))
        key = candidate_key(candidate)
        existing = next((row for row in owned if candidate_key({"kind": row.kind, "slug": row.slug, "url": row.url}) == key), None)
        if existing:
            return source_view(existing)
        if len(owned) >= 2000:
            raise HTTPException(409, "Source quota reached (2,000 per account)")
        row = Source(owner_id=user.id, kind=candidate["kind"], slug=candidate["slug"], company=candidate["company"], url=candidate.get("url"), enabled=True, permitted=data.permitted, interval_seconds=21600)
        db.add(row); db.flush()
        event(db, user.id, "discovered_source_enabled", "Enabled a discovered source after read-only permission review: " + candidate["company"])
        db.commit()
        return source_view(row)

    @router.post("/discovery/source-candidates/{candidate_id}/dismiss")
    def dismiss_candidate(candidate_id: str, request: Request, user=Depends(current_user), db: Session=Depends(get_db)):
        require_locked_session(request, user, db)
        if candidate_id not in candidate_rows(db, user.id):
            raise HTTPException(404, "Source suggestion not found")
        for row in db.scalars(select(Source).where(Source.owner_id == user.id).order_by(Source.id).with_for_update()):
            cache = row.cache or {}
            if any(item.get("id") == candidate_id for item in cache.get("source_candidates", [])[:40] if isinstance(item, dict)):
                dismissed = list(dict.fromkeys([*cache.get("dismissed_source_candidate_ids", []), candidate_id]))[-500:]
                row.cache = {**cache, "dismissed_source_candidate_ids": dismissed}
        db.commit()
        return {"dismissed": True}

    @router.get("/sources/catalog")
    def source_catalog(user=Depends(current_user),db:Session=Depends(get_db)):
        from .source_catalog import catalog
        owned = {(row.kind,row.slug) for row in db.scalars(select(Source).where(Source.owner_id==user.id))}
        return [{**entry,"installed":(entry["source"]["kind"],entry["source"]["slug"]) in owned} for entry in catalog()]

    @router.post("/sources/catalog/{key}")
    def install_source(key:str,request:Request,user=Depends(current_user),db:Session=Depends(get_db)):
        from .source_catalog import catalog
        require_locked_session(request,user,db)
        entry = next((item for item in catalog() if item["key"]==key),None)
        if not entry:
            raise HTTPException(404,"Unknown catalog source")
        if entry["requires_key"]:
            raise HTTPException(409,"Configure BRAVE_SEARCH_API_KEY before enabling this authorized search source")
        data = entry["source"]
        existing = db.scalar(select(Source).where(Source.owner_id==user.id,Source.kind==data["kind"],Source.slug==data["slug"]))
        if existing:
            return source_view(existing)
        if db.scalar(select(func.count()).select_from(Source).where(Source.owner_id==user.id))>=2000:
            raise HTTPException(409,"Source quota reached")
        row = Source(owner_id=user.id,**data)
        db.add(row);db.flush()
        event(db,user.id,"source_catalog_installed","Added a permitted India source configuration: "+entry["label"])
        db.commit()
        return source_view(row)

    @router.get("/operations")
    def operations(user=Depends(current_user),db:Session=Depends(get_db)):
        cutoff = (datetime.now(timezone.utc)-timedelta(days=1)).isoformat()
        counts = dict(db.execute(select(CrawlRun.outcome,func.count()).where(CrawlRun.owner_id==user.id,CrawlRun.started_at>=cutoff).group_by(CrawlRun.outcome)).all())
        durations = sorted(db.scalars(select(CrawlRun.seconds).where(CrawlRun.owner_id==user.id,CrawlRun.started_at>=cutoff,CrawlRun.seconds!=None).order_by(CrawlRun.started_at.desc()).limit(1000)))
        records = db.scalar(select(func.sum(CrawlRun.records)).where(CrawlRun.owner_id==user.id,CrawlRun.started_at>=cutoff)) or 0
        recent = db.scalars(select(CrawlRun).where(CrawlRun.owner_id==user.id).order_by(CrawlRun.started_at.desc()).limit(30))
        completed = sum(counts.get(key,0) for key in ("success","cached","error"))
        oldest = db.scalar(select(func.min(Task.created_at)).where(Task.owner_id==user.id,Task.status=="queued"))
        return {"worker":worker_status(db,user.id),"sources":db.scalar(select(func.count()).select_from(Source).where(Source.owner_id==user.id)),
                "enabled_sources":db.scalar(select(func.count()).select_from(Source).where(Source.owner_id==user.id,Source.enabled==True,Source.permitted==True)),
                "window_hours":24,"scans":counts,"records_received":records,"success_rate":round(100*(counts.get("success",0)+counts.get("cached",0))/completed,1) if completed else None,
                "duration_sample_size":len(durations),"p95_seconds":round(durations[min(len(durations)-1,int(len(durations)*.95))],3) if durations else None,
                "oldest_queued_at":oldest,"database_mode":"distributed_postgresql" if settings.database_url.startswith("postgresql") else "single_machine_sqlite",
                "shared_host_limits":settings.distributed_rate_limits and settings.database_url.startswith("postgresql"),"worker_roles":list(settings.worker_kinds),
                "browser_limit_per_process":settings.browser_concurrency,"configured_concurrency_per_process":settings.concurrency,
                "recent_scans":[{key:getattr(row,key) for key in ("id","source_id","started_at","finished_at","seconds","records","outcome")} for row in recent],
                "external_submission_supported":False,"application_note":"External final submission requires a certified employer integration; available external workflows prepare drafts and specifically approved uploads."}

    @router.post("/sources/bulk")
    async def bulk(data:SourceBatch,request:Request,user=Depends(current_user),db:Session=Depends(get_db)):
        semaphore = asyncio.Semaphore(10)
        async def check(source):
            if source.url:
                async with semaphore:
                    try:
                        await validate_public_url(source.url)
                    except ValueError:
                        raise HTTPException(422,"One or more source URLs are not permitted public destinations") from None
        await asyncio.gather(*(check(source) for source in data.sources))
        require_locked_session(request,user,db)
        owned = list(db.scalars(select(Source).where(Source.owner_id==user.id)))
        keys = {(row.kind,row.slug,row.url or "") for row in owned}
        additions = []
        for source in data.sources:
            key = (source.kind,source.slug,source.url or "")
            if key not in keys:
                additions.append(source);keys.add(key)
        if len(owned)+len(additions)>2000:
            raise HTTPException(409,"Source quota reached (2,000 per account)")
        rows = [Source(owner_id=user.id,**source.model_dump()) for source in additions]
        db.add_all(rows);db.flush()
        event(db,user.id,"sources_imported",f"Added {len(rows)} source configurations; existing permissions and schedules preserved")
        db.commit()
        return {"added":len(rows),"skipped":len(data.sources)-len(rows),"sources":[source_view(row) for row in rows]}

    return router
