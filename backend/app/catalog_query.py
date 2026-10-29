"""Indexed authorized SQL reads. v1 semantics remain in opportunity_query.py."""
import hashlib
import json
from datetime import datetime, timezone

from cryptography.fernet import InvalidToken
from fastapi import HTTPException
from sqlalchemy import select, func, or_, and_, literal_column, union_all
from sqlalchemy.orm import aliased, lazyload

from .models import Opportunity, Source, SourceOpportunity, SavedOpportunity
from .security import fernet, decrypt
from .catalog_projection import instant


def visible_ids(owner_id, saved=False):
    """Resolve private legacy IDs without admitting other owners' aliases."""
    linked = aliased(Opportunity)
    canonical = func.coalesce(linked.canonical_id, linked.id)
    if saved:
        return select(canonical).join(SavedOpportunity, SavedOpportunity.opportunity_id == linked.id).where(SavedOpportunity.owner_id == owner_id)
    return select(canonical).join(SourceOpportunity, SourceOpportunity.opportunity_id == linked.id).join(Source, Source.id == SourceOpportunity.source_id).where(Source.owner_id == owner_id)


def visible_predicate(owner_id, saved=False):
    """Bounded-data membership sets, including this owner's legacy aliases.

    Canonical IDs can be read directly from the narrow membership table. Only
    aliases need the additional opportunity join; no JSON fact rows are read
    to resolve ordinary IDs. UNION ALL is safe inside a semi-join (IN).
    """
    alias = aliased(Opportunity)
    if saved:
        direct = select(SavedOpportunity.opportunity_id).where(SavedOpportunity.owner_id == owner_id)
        historical = select(alias.canonical_id).join(SavedOpportunity, SavedOpportunity.opportunity_id == alias.id)\
            .where(alias.canonical_id.is_not(None), SavedOpportunity.owner_id == owner_id)
    else:
        direct = select(SourceOpportunity.opportunity_id).join(Source, Source.id == SourceOpportunity.source_id)\
            .where(Source.owner_id == owner_id)
        historical = select(alias.canonical_id).join(SourceOpportunity, SourceOpportunity.opportunity_id == alias.id)\
            .join(Source, Source.id == SourceOpportunity.source_id)\
            .where(alias.canonical_id.is_not(None), Source.owner_id == owner_id)
    return Opportunity.id.in_(union_all(direct, historical))


def indexed_query(owner_id, *, saved=False, kind="", company="", search="", location="", remote=False,
                  include_closed=False, deadline_before=None, search_mode="substring", at=None):
    at = at or datetime.now(timezone.utc)
    query = select(Opportunity).options(lazyload(Opportunity.canonical)).where(visible_predicate(owner_id, saved),
        Opportunity.catalog_scope.in_(("public", "private:" + owner_id, "legacy")),
        Opportunity.canonical_id.is_(None), Opportunity.projection_version == 1)
    if kind:
        query = query.where(Opportunity.kind == kind)
    if not include_closed:
        query = query.where(Opportunity.active_flag == True, or_(Opportunity.expires_at.is_(None), Opportunity.expires_at > at))
    if remote:
        query = query.where(Opportunity.remote_flag == True)
    if company:
        query = query.where(Opportunity.company_key.contains(company.casefold(), autoescape=True))
    if location:
        query = query.where(Opportunity.location_key.contains(location.casefold(), autoescape=True))
    if search:
        if search_mode == "text":
            vector = func.to_tsvector(literal_column("'simple'"), func.coalesce(Opportunity.search_document, literal_column("''")))
            query = query.where(vector.op("@@")(func.websearch_to_tsquery(literal_column("'simple'"), search)))
        else:
            query = query.where(Opportunity.search_document.contains(search.casefold(), autoescape=True))
    if deadline_before:
        query = query.where(Opportunity.deadline_at <= deadline_before)
    return query


def encode_cursor(payload):
    return fernet.encrypt(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).decode()


def decode_cursor(token, owner_id, filter_hash):
    try:
        result = json.loads(fernet.decrypt(token.encode(), ttl=3600))
        if result["version"] != 1 or result["owner"] != owner_id or result["filter_hash"] != filter_hash:
            raise ValueError
        if not isinstance(result["id"], str) or len(result["id"]) > 100 or not instant(result["as_of"]):
            raise ValueError
        if result["key"] is not None and not instant(result["key"]):
            raise ValueError
        return result
    except (InvalidToken, ValueError, KeyError, TypeError, UnicodeError):
        raise HTTPException(422, "Cursor is invalid, expired, or belongs to another query/account") from None


def cursor_page(db, user, *, cursor="", page_size=20, sort="newest", kind="", company="", search="",
                location="", remote=False, saved=False, include_closed=False, search_mode="substring"):
    from .services import job_view
    from .opportunity_query import _decorate
    if search_mode == "text" and db.get_bind().dialect.name != "postgresql":
        raise HTTPException(422, "Full-text mode requires PostgreSQL; substring mode is available locally")
    options = dict(sort=sort, kind=kind, company=company, search=search, location=location, remote=remote,
                   saved=saved, include_closed=include_closed, search_mode=search_mode, page_size=page_size)
    fingerprint = hashlib.sha256(json.dumps(options, sort_keys=True).encode()).hexdigest()
    state = decode_cursor(cursor, user.id, fingerprint) if cursor else None
    at = instant(state["as_of"]) if state else datetime.now(timezone.utc)
    # An additive upgrade never hides old records: request the explicit indexing
    # operation rather than quietly omitting unprojected visible facts.
    pending = db.scalar(select(Opportunity.id).where(visible_predicate(user.id, saved),
        Opportunity.canonical_id.is_(None), Opportunity.projection_version != 1).limit(1))
    if pending:
        raise HTTPException(409, "Catalog indexing is pending; run python -m app.catalog_migrations backfill. The v1 API remains available.")
    query = indexed_query(user.id, saved=saved, kind=kind, company=company, search=search, location=location,
        remote=remote, include_closed=include_closed, search_mode=search_mode)
    # first_discovered is generated in UTC by the server, immutable across upserts.
    query = query.where(Opportunity.first_discovered <= at.isoformat())
    if sort == "newest":
        if state:
            key = instant(state["key"])
            query = query.where(or_(Opportunity.sort_at < key, and_(Opportunity.sort_at == key, Opportunity.id < state["id"])))
        query = query.order_by(Opportunity.sort_at.desc(), Opportunity.id.desc())
    else:
        if state:
            key = instant(state["key"])
            predicate = and_(Opportunity.deadline_at.is_(None), Opportunity.id > state["id"]) if key is None else or_(
                Opportunity.deadline_at > key, and_(Opportunity.deadline_at == key, Opportunity.id > state["id"]), Opportunity.deadline_at.is_(None))
            query = query.where(predicate)
        query = query.order_by(Opportunity.deadline_at.asc().nulls_last(), Opportunity.id.asc())
    rows = list(db.scalars(query.limit(page_size + 1)))
    more, rows = len(rows) > page_size, rows[:page_size]
    profile = decrypt(user.profile_encrypted)
    fields = {"id", "title", "company", "url", "location", "remote", "opportunity_type", "compensation", "deadline",
              "published_at", "first_discovered", "last_verified", "status", "score", "eligibility", "reasons", "source", "verification_status", "is_demo"}
    compact = [{k:v for k,v in job_view(row, profile).items() if k in fields} for row in rows]
    next_cursor = None
    if more and rows:
        last = rows[-1]
        key = last.sort_at if sort == "newest" else last.deadline_at
        next_cursor = encode_cursor({"version":1, "owner":user.id, "filter_hash":fingerprint, "as_of":at.isoformat(),
            "id":last.id, "key":instant(key).isoformat() if key is not None else None})
    return {"items":_decorate(db, user.id, compact), "next_cursor":next_cursor, "has_more":more,
            "as_of":at.isoformat(), "search_mode":search_mode, "personalized_sort":False}
