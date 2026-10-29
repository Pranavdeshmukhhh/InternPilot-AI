"""Owner-scoped opportunity browsing with bounded evaluation and SQL prefilters.

Chronological pages do not need profile scoring to select their records. Filter
candidate facts in bounded scalar batches, retain only the requested sort window,
then hydrate/evaluate that page. Matching/recommendation filters still evaluate
every candidate for correctness; bounded heaps avoid retaining every large view.
"""
from __future__ import annotations

import heapq
from datetime import date, datetime, timezone

from fastapi import HTTPException
from sqlalchemy import String, case, cast, func, literal, or_, select

from .discovery_filters import matches as matches_criteria
from .geography import classify, location_matches
from .matching import _disclosed_paid
from .models import Application, Opportunity, SavedOpportunity
from .opportunity_intelligence import _positive_prize
from .security import decrypt
from .services import job_view, timestamp

BATCH_SIZE = 200


def _ascii_prefilter(expression, query, dialect):
    """A conservative prefilter; exact Unicode casefold is checked in Python.

    SQL lower() differs from Python casefold (e.g. Straße/STRASSE). Non-ASCII
    data passes this prefilter so database collation never hides a valid match.
    Non-ASCII search terms skip this optimization entirely.
    """
    if not query.isascii() or dialect not in {"sqlite", "postgresql"}:
        return None
    non_ascii = expression.op("GLOB")("*[^ -~]*") if dialect == "sqlite" else expression.op("~")("[^ -~]")
    return or_(func.lower(expression).contains(query.lower(), autoescape=True), non_ascii)


def candidate_query(db, owner_id, *, saved=False, kind="", remote="", company="", search=""):
    if saved:
        ids = select(SavedOpportunity.opportunity_id).where(SavedOpportunity.owner_id == owner_id)
    else:
        from .catalog_query import visible_ids
        ids = visible_ids(owner_id)
    query = select(Opportunity).where(Opportunity.id.in_(ids))
    if kind:
        query = query.where(func.coalesce(Opportunity.data["opportunity_type"].as_string(), "internship") == kind)
    dialect = db.get_bind().dialect.name
    if str(remote).lower() in {"true", "1"}:
        # A public feed may contain a string or malformed value. Text conversion
        # cannot throw PostgreSQL's invalid BOOL cast; exact `is True` follows.
        query = query.where(cast(Opportunity.data["remote"].as_string(), String).in_(("true", "1")))

    def field_text(key):
        value = Opportunity.data[key].as_string()
        # Python's existing search treats missing fields as '' and explicit
        # null as 'None'. Preserve separators in cross-field searches exactly.
        typ = func.json_type(Opportunity.data, f"$.{key}") if dialect == "sqlite" else func.json_typeof(Opportunity.data[key])
        return case((typ == "null", "None"), else_=func.coalesce(value, ""))

    if company:
        expression = field_text("company")
        predicate = _ascii_prefilter(expression, company, dialect)
        if predicate is not None:
            query = query.where(predicate)
    if search:
        fields = [field_text(key) for key in ("title", "company", "description", "location")]
        expression = fields[0]
        for field in fields[1:]:
            expression = expression + literal(" ") + field
        predicate = _ascii_prefilter(expression, search, dialect)
        if predicate is not None:
            query = query.where(predicate)
    # Stable ties make page navigation deterministic, including equal scores.
    return query.order_by(Opportunity.id)


def _cutoff(value):
    if not value:
        return None
    try:
        return datetime.combine(date.fromisoformat(value), datetime.max.time(), tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(422, "Deadline filter must be YYYY-MM-DD") from None


def _raw_matches(data, profile, options, cutoff, at):
    kind = data.get("opportunity_type", "internship")
    expiry = timestamp(data.get("deadline")) or (timestamp(data.get("ends_at")) if kind == "hackathon" else None)
    if not options.get("include_closed") and (data.get("active") is False or expiry and expiry <= at):
        return False
    if options.get("kind") and kind != options["kind"]:
        return False
    if options.get("search") and options["search"].casefold() not in " ".join(str(data.get(key, "")) for key in ("title", "company", "description", "location")).casefold():
        return False
    if options.get("company") and options["company"].casefold() not in str(data.get("company", "")).casefold():
        return False
    nearby = profile.get("include_nearby_locations", True)
    if options.get("location") and not location_matches(data, options["location"], nearby):
        return False
    if options.get("region", "all") != "all" and options["region"] not in classify(data, profile)["regions"]:
        return False
    if options.get("criteria") and not matches_criteria(data, options["criteria"]):
        return False
    if str(options.get("remote", "")).lower() in {"true", "1"} and data.get("remote") is not True:
        return False
    if str(options.get("paid", "")).lower() in {"true", "1"}:
        paid = _positive_prize(str(data.get("description") or "") + " " + str(data.get("compensation") or "")) if kind == "hackathon" else _disclosed_paid(data.get("compensation"))
        if not paid:
            return False
    if cutoff and not (timestamp(data.get("deadline")) and timestamp(data["deadline"]) <= cutoff):
        return False
    return True


def _sort_key(data, first_discovered, sort):
    if sort == "deadline":
        return timestamp(data.get("deadline")) or datetime.max.replace(tzinfo=timezone.utc)
    freshness = data.get("published_at") or first_discovered
    return freshness if sort == "newest" else (data["score"], freshness)


def _decorate(db, owner_id, rows):
    # Limit parameter counts for SQLite and avoid loading the owner's complete
    # application/bookmark history for a single page.
    saved, statuses = set(), {}
    ids = [row["id"] for row in rows]
    target = func.coalesce(Opportunity.canonical_id, Opportunity.id)
    for start in range(0, len(ids), BATCH_SIZE):
        chunk = ids[start:start + BATCH_SIZE]
        saved_rows = db.execute(select(SavedOpportunity.opportunity_id, target).join(Opportunity, Opportunity.id == SavedOpportunity.opportunity_id)
            .where(SavedOpportunity.owner_id == owner_id, or_(SavedOpportunity.opportunity_id.in_(chunk), target.in_(chunk))))
        for legacy, canonical in saved_rows:
            saved.update((legacy, canonical))
        application_rows = db.execute(select(Application.opportunity_id, target, Application.status).join(Opportunity, Opportunity.id == Application.opportunity_id)
            .where(Application.owner_id == owner_id, or_(Application.opportunity_id.in_(chunk), target.in_(chunk))).order_by(Application.created_at))
        for legacy, canonical, status in application_rows:
            statuses[legacy] = statuses[canonical] = status
    return [{**row, "saved": row["id"] in saved, "application_status": statuses.get(row["id"], "not_started")} for row in rows]


def query_opportunities(db, user, *, page=None, page_size=20, view=job_view, **options):
    """Return the original list API or the original numbered-page response."""
    profile = decrypt(user.profile_encrypted)
    cutoff, at = _cutoff(options.get("deadline_before", "")), datetime.now(timezone.utc)
    sort = options.get("sort", "score")
    base = candidate_query(db, user.id, **{key: options.get(key, False if key == "saved" else "") for key in ("saved", "kind", "remote", "company", "search")})
    offset = (page - 1) * page_size if page is not None else 0
    window = offset + page_size if page is not None else None
    computed_filter = bool(options.get("eligibility") or options.get("recommended") or options.get("min_score", 0))
    chronological = page is not None and sort in {"newest", "deadline"} and not computed_filter
    criteria = options.get("criteria")
    criteria_active = bool(criteria and any(criteria.model_dump().values()))
    simple = chronological and not criteria_active and not options.get("location") and options.get("region", "all") == "all" and not options.get("paid")
    if simple:
        # Exact legacy totals remain SQL COUNT, not a Python facts/evaluation scan.
        # Unprojected or historical-alias fixtures retain the v1 fallback until
        # explicitly backfilled; this preserves every existing API contract.
        needs_fallback = db.scalar(base.with_only_columns(Opportunity.id).order_by(None)
            .where(or_(Opportunity.projection_version != 1, Opportunity.canonical_id.is_not(None))).limit(1))
        if needs_fallback is None:
            from .catalog_query import indexed_query
            query = indexed_query(user.id, saved=options.get("saved", False), kind=options.get("kind", ""),
                company=options.get("company", ""), search=options.get("search", ""),
                remote=str(options.get("remote", "")).lower() in {"true", "1"}, include_closed=options.get("include_closed", False), deadline_before=cutoff, at=at)
            total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
            ordered = query.order_by(Opportunity.deadline_at.asc().nulls_last(), Opportunity.id.asc()) if sort == "deadline" else query.order_by(Opportunity.sort_at.desc(), Opportunity.id.asc())
            chosen = [view(job, profile) for job in db.scalars(ordered.offset(offset).limit(page_size))]
            return {"items":_decorate(db, user.id, chosen), "total":total, "page":page, "page_size":page_size}
    total = 0

    def candidates():
        nonlocal total
        if chronological:
            # Scalar batches avoid filling the ORM identity map with candidates.
            query = base.with_only_columns(Opportunity.id, Opportunity.data, Opportunity.first_discovered)
            for ident, data, discovered in db.execute(query.execution_options(yield_per=BATCH_SIZE)):
                if _raw_matches(data, profile, options, cutoff, at):
                    total += 1
                    yield {"id": ident, "sort_key": _sort_key(data, discovered, sort)}
        else:
            for job in db.scalars(base.execution_options(yield_per=BATCH_SIZE)):
                if not _raw_matches(job.data, profile, options, cutoff, at):
                    continue
                row = view(job, profile)
                if options.get("eligibility") and row["eligibility"] != options["eligibility"]:
                    continue
                minimum = max(50, options.get("min_score", 0)) if options.get("recommended") else options.get("min_score", 0)
                if row["score"] < minimum or options.get("recommended") and row["eligibility"] == "ineligible":
                    continue
                total += 1
                yield row

    key = (lambda row: row["sort_key"]) if chronological else (lambda row: _sort_key(row, row["first_discovered"], sort))
    if window is None:
        chosen = sorted(candidates(), key=key, reverse=sort != "deadline")
    elif sort == "deadline":
        chosen = heapq.nsmallest(window, candidates(), key=key)[offset:]
    else:
        chosen = heapq.nlargest(window, candidates(), key=key)[offset:]
    if chronological:
        ids = [item["id"] for item in chosen]
        jobs = {row.id: row for row in db.scalars(select(Opportunity).where(Opportunity.id.in_(ids)))} if ids else {}
        chosen = [view(jobs[ident], profile) for ident in ids]
    items = _decorate(db, user.id, chosen)
    return items if page is None else {"items": items, "total": total, "page": page, "page_size": page_size}
