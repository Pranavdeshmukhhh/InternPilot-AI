"""Additive v6 schema and resumable projection/recovery operations.

No legacy ID, reference, fact, credential or private payload is removed by upgrade.
Recovery materializes aliases before old code is allowed to read the database.
"""
import argparse
import hashlib
import json

from sqlalchemy import inspect, select, update, text, bindparam

from .catalog_projection import projection


def source_key(config):
    # Personal display labels and ignored URL fields do not identify an ATS API.
    # Public company attribution comes from the reviewed config, never that label.
    fields = {k: config.get(k) or "" for k in ("kind", "slug", "url")}
    if fields["kind"] in {"greenhouse", "lever", "ashby", "smartrecruiters"}:
        fields["url"] = ""
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


def upgrade_schema(conn):
    from .models import Opportunity, CatalogSource, CatalogListing, OpportunityArchive
    existing = {c["name"] for c in inspect(conn).get_columns("opportunities")}
    source_columns = {c["name"] for c in inspect(conn).get_columns("sources")}
    if "scan_generation" not in source_columns:
        conn.execute(text("ALTER TABLE sources ADD COLUMN scan_generation INTEGER NOT NULL DEFAULT 0"))
    additions = {
        "canonical_id": "VARCHAR(36) REFERENCES opportunities(id)",
        "catalog_scope": "VARCHAR(100) NOT NULL DEFAULT 'legacy'",
        "projection_version": "INTEGER NOT NULL DEFAULT 0", "authority_rank":"INTEGER NOT NULL DEFAULT 0", "kind": "VARCHAR(30)",
        "company_key": "TEXT", "search_document": "TEXT", "location_key": "TEXT", "url_key":"VARCHAR(64)",
        "remote_flag": "BOOLEAN", "active_flag": "BOOLEAN",
        "expires_at": "TIMESTAMP WITH TIME ZONE" if conn.dialect.name == "postgresql" else "DATETIME",
        "deadline_at": "TIMESTAMP WITH TIME ZONE" if conn.dialect.name == "postgresql" else "DATETIME",
        "sort_at": "TIMESTAMP WITH TIME ZONE" if conn.dialect.name == "postgresql" else "DATETIME",
    }
    for name, sqltype in additions.items():
        if name not in existing:
            conn.execute(text(f"ALTER TABLE opportunities ADD COLUMN {name} {sqltype}"))
    CatalogSource.__table__.create(conn, checkfirst=True)
    CatalogListing.__table__.create(conn, checkfirst=True)
    OpportunityArchive.__table__.create(conn, checkfirst=True)
    for table in (Opportunity.__table__,):
        for index in table.indexes:
            # Existing PostgreSQL data is indexed online by the explicit command.
            # Fresh create_all databases already have their empty-table indexes.
            if conn.dialect.name != "postgresql":
                index.create(conn, checkfirst=True)
    from .models import SourceOpportunity, Application, SavedOpportunity
    for table in (SourceOpportunity.__table__, Application.__table__, SavedOpportunity.__table__):
        for index in table.indexes:
            index.create(conn, checkfirst=True)
    # Built-in configurations are code-reviewed public publishers. Custom sources
    # require an explicit operator approval; a user's checkbox never adds rows here.
    from .discovery import default_sources
    for config in default_sources():
        key = source_key(config)
        if not conn.scalar(select(CatalogSource.id).where(CatalogSource.id == key)):
            approved = {k: config.get(k) for k in ("kind", "slug", "company", "url")}
            approved["min_interval_seconds"] = config.get("interval_seconds", 900)
            conn.execute(CatalogSource.__table__.insert().values(id=key, config=approved))


def backfill(bind, batch_size=500):
    """Keyset batches in separate transactions; safe to resume, no promotion."""
    from .models import Opportunity
    table = Opportunity.__table__
    count = 0
    while True:
        with bind.begin() as conn:
            rows = conn.execute(select(table.c.id, table.c.data, table.c.first_discovered)
                .where(table.c.projection_version == 0, table.c.canonical_id.is_(None))
                .order_by(table.c.id).limit(batch_size)).all()
            if not rows:
                return count
            updates = [{"row_id":ident, **projection(payload, discovered)} for ident, payload, discovered in rows]
            fields = {key:bindparam(key) for key in updates[0] if key != "row_id"}
            conn.execute(update(table).where(table.c.id == bindparam("row_id"), table.c.projection_version == 0,
                table.c.canonical_id.is_(None)).values(**fields), updates)
            count += len(rows)


def build_indexes(bind, *, trigram=False):
    """Online PostgreSQL index build, separate from migration transactions."""
    from .models import Opportunity
    from sqlalchemy.schema import CreateIndex
    if bind.dialect.name != "postgresql":
        return {"database":"sqlite", "full_text":False}
    with bind.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.exec_driver_sql("SET lock_timeout = '5s'")
        try:
            for index in Opportunity.__table__.indexes:
                sql = str(CreateIndex(index, if_not_exists=True).compile(dialect=bind.dialect))
                invalid = conn.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.relname=:name AND n.nspname=current_schema() AND NOT i.indisvalid)"), {"name":index.name})
                if invalid:
                    conn.exec_driver_sql("DROP INDEX CONCURRENTLY " + bind.dialect.identifier_preparer.quote(index.name))
                conn.exec_driver_sql(sql.replace(" INDEX ", " INDEX CONCURRENTLY ", 1))
            invalid = conn.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.relname='ix_catalog_fulltext' AND n.nspname=current_schema() AND NOT i.indisvalid)"))
            if invalid:
                conn.exec_driver_sql("DROP INDEX CONCURRENTLY ix_catalog_fulltext")
            conn.exec_driver_sql("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_catalog_fulltext ON opportunities USING gin (to_tsvector('simple', coalesce(search_document, ''))) WHERE projection_version=1 AND canonical_id IS NULL")
            if trigram:
                conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS pg_trgm")
                conn.exec_driver_sql("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_catalog_company_trgm ON opportunities USING gin (company_key gin_trgm_ops) WHERE projection_version=1 AND canonical_id IS NULL")
        finally:
            # Cancellation/connection loss invalidates the handle. Trying RESET
            # then hides the original failure behind PendingRollbackError.
            if not conn.invalidated:
                conn.exec_driver_sql("RESET lock_timeout")
    return {"database":"postgresql", "full_text":True, "trigram":trigram}


def materialize_aliases(bind, batch_size=500):
    """Non-destructive recovery for v5 readers; original IDs/links stay intact.

    Stop all writers first. Leaves additive v6 columns/tables in place and records
    schema version 6: old data is readable, but old writers must not run alongside
    catalog writers. Restore a full backup for a physical v5 schema downgrade.
    """
    from .models import Opportunity, OpportunityArchive
    from .security import decrypt
    table = Opportunity.__table__
    canonical = table.alias("facts")
    count = 0
    while True:
        with bind.begin() as conn:
            rows = conn.execute(select(table.c.id, canonical.c.data, OpportunityArchive.payload_encrypted)
                .join(canonical, canonical.c.id == table.c.canonical_id)
                .outerjoin(OpportunityArchive, OpportunityArchive.opportunity_id == table.c.id)
                .order_by(table.c.id).limit(batch_size)).all()
            if not rows:
                return count
            for ident, payload, archived in rows:
                payload = decrypt(archived) if archived else payload
                conn.execute(update(table).where(table.c.id == ident).values(data=payload, canonical_id=None, projection_version=0))
            count += len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["backfill", "materialize-aliases", "indexes", "approve-ats", "revoke"])
    parser.add_argument("--writers-stopped", action="store_true")
    parser.add_argument("--trigram", action="store_true", help="Enable only after measuring repeated company substring queries")
    parser.add_argument("--source-id")
    parser.add_argument("--confirm-public-review", action="store_true")
    args = parser.parse_args()
    if args.operation == "materialize-aliases" and not args.writers_stopped:
        parser.error("recovery requires --writers-stopped and a verified backup")
    from .database import engine
    if args.operation in {"approve-ats", "revoke"}:
        if not args.source_id or not args.confirm_public_review:
            parser.error("Operator source review requires --source-id and --confirm-public-review")
        from .database import SessionLocal
        from .models import Source, CatalogSource, now
        from .discovery import _slug
        with SessionLocal() as db:
            source = db.get(Source, args.source_id)
            if source is None:
                parser.error("Source not found")
            config = {k:getattr(source, k) for k in ("kind", "slug", "company", "url")}
            key = source_key(config)
            registry = db.get(CatalogSource, key)
            if args.operation == "approve-ats":
                if source.kind not in {"greenhouse", "lever", "ashby", "smartrecruiters"} or not source.permitted or source.url:
                    parser.error("Only reviewed public ATS API slugs without custom URLs may be approved")
                _slug(config)
                config["min_interval_seconds"] = max(300, source.interval_seconds)
                if registry is None:
                    db.add(CatalogSource(id=key, config=config))
                else:
                    registry.enabled = True
            else:
                if registry is None:
                    parser.error("No reviewed public registry entry exists")
                registry.enabled, registry.lease_token, registry.lease_until = False, None, None
            from .services import event
            event(db, source.owner_id, "catalog_policy", f"Operator {args.operation} for reviewed public catalog source at {now()}")
            db.commit()
            result = {"catalog_source_id":key, "enabled":args.operation == "approve-ats"}
    else:
        result = build_indexes(engine, trigram=args.trigram) if args.operation == "indexes" else backfill(engine) if args.operation == "backfill" else materialize_aliases(engine)
    print(json.dumps({"operation": args.operation, "processed": result}))


if __name__ == "__main__":
    main()
