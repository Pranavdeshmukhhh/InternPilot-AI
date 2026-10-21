"""Versioned schema migration runner; migrations are serialized by PostgreSQL lock.

Version 1 is the initial schema. Future schema changes must add numbered migration
functions instead of modifying existing persisted schema with create_all.
"""
from sqlalchemy import text, inspect
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
                        conn.execute(models.Source.__table__.insert().values(owner_id=owner,kind=kind,slug="",company=company,url=url,permitted=True,enabled=True,interval_seconds=interval))
            conn.execute(models.SchemaVersion.__table__.insert().values(version=3, applied_at=models.now()))


if __name__ == "__main__":
    migrate()
    print("Database schema is current (version 3).")
