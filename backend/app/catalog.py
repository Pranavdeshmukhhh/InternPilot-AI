"""Scoped, batched catalog writes and reviewed public-source coordination.

Facts are shared only after an operator-reviewed source configuration matches
exactly. Personal answers, scores, profiles and imported records never enter it.
Historical IDs are retained as private compatibility aliases with encrypted
pre-consolidation evidence.
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select, delete, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .catalog_migrations import source_key
from .catalog_projection import projection, instant
from .models import Opportunity, OpportunityArchive, SourceOpportunity, CatalogSource, CatalogListing, now
from .security import digest, encrypt

BATCH_SIZE = 200
PUBLIC_FIELDS = frozenset({
    "external_id", "title", "company", "location", "remote", "url", "description", "skills", "requirements",
    "published_at", "source_created_at", "deadline", "compensation", "adjacent_student_role", "active", "source",
    "source_url", "opportunity_type", "starts_at", "ends_at", "registration_status", "verification_status",
    "verification_note", "verification_evidence_url", "application_url_verified", "official_url", "organizer",
    "venue_country", "format_type", "published_date", "discovered_via", "llm_analysis",
})


def insert_for(db, table):
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        return pg_insert(table)
    if dialect == "sqlite":
        return sqlite_insert(table)
    raise RuntimeError("Catalog upserts require PostgreSQL or local SQLite")


def reviewed_source(db, source):
    config = {k: getattr(source, k) for k in ("kind", "slug", "company", "url")}
    return db.scalar(select(CatalogSource).where(CatalogSource.id == source_key(config)))


def ingest(db, owner_id, source, records, *, public=False, verified_at=None, link_only=False):
    """One transaction, O(batches) statements, database-unique identity.

    Caller owns the transaction and public scan fence. Private callers cannot
    select public identity by providing the same URL. Locks are ordered by key.
    """
    from .services import canonical_fingerprint, merge_opportunity_data
    if source.owner_id != owner_id:
        raise PermissionError("Source is not owned by the ingestion account")
    registry = reviewed_source(db, source) if public else None
    if public and (not source.enabled or not source.permitted or registry is None or not registry.enabled):
        raise PermissionError("Public ingestion requires an enabled operator-reviewed source")
    verified_at = verified_at or now()
    records_by_key = {}
    for original in records:
        data = {**original, "active":original.get("active", True), "source":original.get("source") or source.kind,
                "source_url":original.get("source_url") or (None if public else source.url) or original.get("url"),
                "opportunity_type":original.get("opportunity_type", "internship")}
        if public:
            data = {k:v for k,v in data.items() if k in PUBLIC_FIELDS}
            if source.kind in {"greenhouse", "lever", "ashby", "smartrecruiters"}:
                data["company"] = registry.config["company"]
        key = canonical_fingerprint(data)
        records_by_key[key] = data
    result, aliases, changed, added = [], {}, [], 0
    # All upserts acquire unique-row locks in one global fingerprint order,
    # including across batches. Pre-locking only existing rows can invert that
    # order when another transaction is concurrently inserting unseen rows.
    keys = sorted(records_by_key, key=lambda key:digest(("public:" if public else owner_id + ":") + key))
    for start in range(0, len(keys), BATCH_SIZE):
        batch = keys[start:start + BATCH_SIZE]
        public_fps = {key:digest(("public:" if public else owner_id + ":") + key) for key in batch}
        legacy_fps = {key:digest(owner_id + ":" + key) for key in batch}
        wanted = set(public_fps.values()) | set(legacy_fps.values())
        existing = {r.fingerprint:r for r in db.scalars(select(Opportunity).where(Opportunity.fingerprint.in_(wanted))
            .order_by(Opportunity.fingerprint))}
        rows = []
        for key in batch:
            data = records_by_key[key]
            current = existing.get(public_fps[key])
            verified = True
            if current:
                data, verified = (current.data, False) if link_only else merge_opportunity_data(current.data, data)
                differences = [field for field in ("deadline", "active", "compensation", "eligibility") if current.data.get(field) != data.get(field)]
                if differences:
                    changed.append((current.id, current.data, data, differences))
            discovered = current.first_discovered if current else now()
            published = instant(data.get("published_at"))
            latency = current.discovery_latency_seconds if current else max(0, (datetime.now(timezone.utc) - published).total_seconds()) if published else None
            row = {"id":current.id if current else str(uuid4()), "fingerprint":public_fps[key], "data":data,
                   "catalog_scope":"public" if public else "private:" + owner_id, "canonical_id":None,
                   "first_discovered":discovered, "last_verified":verified_at if verified else current.last_verified,
                   "discovery_latency_seconds":latency, **projection(data, discovered)}
            if not link_only:
                row["authority_rank"] = projection(records_by_key[key], discovered)["authority_rank"]
            rows.append(row)
        if link_only:
            actual = {fp:existing[fp] for fp in public_fps.values()}
        else:
            stmt = insert_for(db, Opportunity.__table__).values(rows)
            updates = {key:getattr(stmt.excluded, key) for key in rows[0] if key not in {"id", "fingerprint", "first_discovered", "discovery_latency_seconds"}}
            # Unique fingerprint handles inserts racing before either sees a row.
            db.execute(stmt.on_conflict_do_update(index_elements=["fingerprint"], set_=updates,
                where=Opportunity.__table__.c.authority_rank <= stmt.excluded.authority_rank))
            actual = {r.fingerprint:r for r in db.scalars(select(Opportunity).where(Opportunity.fingerprint.in_(public_fps.values()))
                .execution_options(populate_existing=True))}
        linked = set(db.scalars(select(SourceOpportunity.opportunity_id).where(SourceOpportunity.source_id == source.id,
            SourceOpportunity.opportunity_id.in_([r.id for r in actual.values()]))))
        links, archives, alias_updates = [], [], []
        for key in batch:
            row = actual[public_fps[key]]
            legacy = existing.get(legacy_fps[key])
            if public and legacy and legacy.id != row.id and not legacy.canonical_id:
                archives.append({"opportunity_id":legacy.id, "owner_id":owner_id, "payload_encrypted":encrypt(legacy.data)})
                aliases[legacy.id] = row.id
                alias_updates.append((legacy.id, row.id))
            if row.id not in linked:
                added += 1
            links.append({"source_id":source.id, "opportunity_id":row.id})
            result.append(row)
        if archives:
            stmt = insert_for(db, OpportunityArchive.__table__).values(archives)
            db.execute(stmt.on_conflict_do_nothing(index_elements=["opportunity_id"]))
            # Bounded executemany; aliases retain the old fingerprint and ID.
            from sqlalchemy import bindparam
            db.execute(update(Opportunity.__table__).where(Opportunity.__table__.c.id == bindparam("alias_id"))
                .values(data={}, canonical_id=bindparam("target_id"), projection_version=0),
                [{"alias_id":a,"target_id":b} for a,b in alias_updates])
            db.execute(delete(SourceOpportunity).where(SourceOpportunity.source_id == source.id,
                SourceOpportunity.opportunity_id.in_(aliases)))
            for legacy in existing.values():
                if legacy.id in aliases:
                    db.expire(legacy)
        if links:
            stmt = insert_for(db, SourceOpportunity.__table__).values(links)
            db.execute(stmt.on_conflict_do_nothing(index_elements=["source_id", "opportunity_id"]))
    return result, added, changed, aliases


def claim_public_scan(db, registry, interval):
    """A lease fences network results; a fresh shared snapshot avoids refetching."""
    row = db.scalar(select(CatalogSource).where(CatalogSource.id == registry.id).with_for_update().execution_options(populate_existing=True))
    if not row.enabled:
        return "paused", row, None
    from .coordination import health_ready
    if not health_ready(db, row.id):
        return "backoff", row, None
    at = datetime.now(timezone.utc)
    interval = max(interval, int((row.config or {}).get("min_interval_seconds", 300)))
    if row.last_success and instant(row.last_success) + timedelta(seconds=interval) > at:
        return "cached", row, None
    if row.lease_until and instant(row.lease_until) > at:
        return "busy", row, None
    token = str(uuid4())
    row.lease_token, row.lease_until = token, (at + timedelta(seconds=180)).isoformat()
    return "fetch", row, token


def cached_public_result(db, registry):
    rows = list(db.scalars(select(Opportunity).join(CatalogListing, CatalogListing.opportunity_id == Opportunity.id)
        .where(CatalogListing.source_id == registry.id, CatalogListing.active == True)))
    return {"jobs":[r.data for r in rows], "cache":registry.cache, "shared_verified_at":registry.last_success}
