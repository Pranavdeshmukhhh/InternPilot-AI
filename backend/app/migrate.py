"""Versioned schema migration runner; migrations are serialized by PostgreSQL lock.

Version 1 is the initial schema. Future schema changes must add numbered migration
functions instead of modifying existing persisted schema with create_all.
"""
from sqlalchemy import text, inspect, Table, MetaData
from .database import Base, engine
from . import models  # noqa: F401


def migrate():
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text("SELECT pg_advisory_xact_lock(721954829)"))
        models.SchemaVersion.__table__.create(conn, checkfirst=True)
        versions = set(conn.execute(text("SELECT version FROM schema_versions")).scalars())
        if 1 not in versions:
            Base.metadata.create_all(conn)
            conn.execute(models.SchemaVersion.__table__.insert().values(version=1, applied_at=models.now()))
        if 2 not in versions:
            models.WorkerHeartbeat.__table__.create(conn, checkfirst=True)
            models.DeadlineReminder.__table__.create(conn, checkfirst=True)
            # New databases already have this column from their initial create;
            # existing version-1 databases require an additive migration.
            columns = {column["name"] for column in inspect(conn).get_columns("notifications")}
            if "opportunity_id" not in columns:
                conn.execute(text("ALTER TABLE notifications ADD COLUMN opportunity_id VARCHAR(36)"))
            conn.execute(models.SchemaVersion.__table__.insert().values(version=2, applied_at=models.now()))
        if 3 not in versions:
            for table in (models.SavedOpportunity, models.NotificationSettings, models.NotificationDelivery):
                table.__table__.create(conn, checkfirst=True)
            additions = {"applications": {"upload_approved_at": "VARCHAR", "upload_approval_digest": "VARCHAR(64)", "upload_started_at": "VARCHAR"},
                         "notifications": {"dedupe_key": "VARCHAR(200)"}}
            for table, new_columns in additions.items():
                existing = {column["name"] for column in inspect(conn).get_columns(table)}
                for column, kind in new_columns.items():
                    if column not in existing:
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {kind}"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_notification_dedupe ON notifications (dedupe_key)"))
            for owner in conn.execute(models.User.__table__.select().with_only_columns(models.User.id)).scalars():
                for kind,company,url,interval in (("mlh","Major League Hacking",None,1800),("internscan","InternScan India feed","https://internscan.vercel.app/in/api/active.json",900)):
                    exists = conn.execute(models.Source.__table__.select().with_only_columns(models.Source.id).where(models.Source.owner_id==owner,models.Source.kind==kind)).first()
                    if not exists:
                        # Freeze legacy data-migration inputs: current ORM defaults
                        # can contain columns absent from a genuine v1/v2 schema.
                        legacy = Table("sources", MetaData(), autoload_with=conn)
                        conn.execute(legacy.insert().values(id=models.uid(),owner_id=owner,kind=kind,slug="",company=company,url=url,
                            permitted=True,enabled=True,interval_seconds=interval,status="pending",failures=0,cache={},discovered_count=0))
            conn.execute(models.SchemaVersion.__table__.insert().values(version=3, applied_at=models.now()))
        if 4 not in versions:
            existing = {column["name"] for column in inspect(conn).get_columns("users")}
            additions = {"role":"VARCHAR(20) NOT NULL DEFAULT 'member'", "disabled":"BOOLEAN NOT NULL DEFAULT false",
                         "last_login_at":"VARCHAR(40)","last_seen_at":"VARCHAR(40)"}
            for column,kind in additions.items():
                if column not in existing:
                    conn.execute(text(f"ALTER TABLE users ADD COLUMN {column} {kind}"))
            conn.execute(models.SchemaVersion.__table__.insert().values(version=4, applied_at=models.now()))
        if 5 not in versions:
            for table in (models.HostBudget,models.CrawlRun,models.GmailConnection,models.GmailOAuthState,models.OutreachSettings,models.OutreachContact,models.OutreachMessage,models.OutreachReply):
                table.__table__.create(conn,checkfirst=True)
            for statement in (
                "CREATE INDEX IF NOT EXISTS ix_sources_due ON sources (enabled, permitted, next_run)",
                "CREATE INDEX IF NOT EXISTS ix_task_claim ON tasks (status, available_at, priority)",
                "CREATE INDEX IF NOT EXISTS ix_outreach_due ON outreach_messages (status, scheduled_at)",
            ):
                conn.execute(text(statement))
            conn.execute(models.SchemaVersion.__table__.insert().values(version=5,applied_at=models.now()))
        if 6 not in versions:
            from .catalog_migrations import upgrade_schema
            upgrade_schema(conn)
            conn.execute(models.SchemaVersion.__table__.insert().values(version=6, applied_at=models.now()))

        if 7 not in versions:
            for table in (models.CoordinationState, models.RequestLease, models.DiscoveryHealth):
                table.__table__.create(conn, checkfirst=True)
            conn.execute(models.SchemaVersion.__table__.insert().values(version=7, applied_at=models.now()))

        if 8 not in versions:
            if conn.scalar(text("SELECT count(*) FROM users WHERE role='owner'")) > 1:
                raise RuntimeError("Multiple owners exist. With all writers stopped, run python -m app.admin select-founder, then migrate again.")
            for table, additions in {"users":{"reset_required":"BOOLEAN NOT NULL DEFAULT false", "security_version":"INTEGER NOT NULL DEFAULT 0"},
                                     "sessions":{"mfa_verified_at":"VARCHAR(40)"}}.items():
                columns = {column["name"] for column in inspect(conn).get_columns(table)}
                for column, kind in additions.items():
                    if column not in columns:
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {kind}"))
            for model in (models.AccountMFA, models.PasswordRecovery, models.SecurityEvent):
                model.__table__.create(conn, checkfirst=True)
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_single_founder ON users (role) WHERE role='owner'"))
            conn.execute(models.SchemaVersion.__table__.insert().values(version=8, applied_at=models.now()))


if __name__ == "__main__":
    migrate()
    print("Database schema is current (version 8). Run python -m app.catalog_migrations backfill for existing projections.")
