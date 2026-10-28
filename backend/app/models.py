from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import String, Text, Integer, Boolean, LargeBinary, JSON, UniqueConstraint, Index, Float
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base


def uid():
    return str(uuid4())


def now():
    return datetime.now(timezone.utc).isoformat()


class HostBudget(Base):
    __tablename__ = "host_budgets"
    host: Mapped[str] = mapped_column(String(253),primary_key=True)
    next_allowed: Mapped[str] = mapped_column(String(40))


class CrawlRun(Base):
    __tablename__ = "crawl_runs"
    id: Mapped[str] = mapped_column(String(36),primary_key=True,default=uid)
    owner_id: Mapped[str] = mapped_column(String(36),index=True)
    source_id: Mapped[str] = mapped_column(String(36),index=True)
    started_at: Mapped[str] = mapped_column(default=now,index=True)
    finished_at: Mapped[str | None] = mapped_column(nullable=True)
    seconds: Mapped[float | None] = mapped_column(Float,nullable=True)
    records: Mapped[int] = mapped_column(default=0)
    outcome: Mapped[str] = mapped_column(String(30),default="running")


class GmailConnection(Base):
    __tablename__ = "gmail_connections"
    owner_id: Mapped[str] = mapped_column(String(36),primary_key=True)
    email_hash: Mapped[str] = mapped_column(String(64),unique=True)
    data_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    status: Mapped[str] = mapped_column(String(30),default="connected")
    last_reserved_at: Mapped[str | None] = mapped_column(nullable=True)
    last_sync_at: Mapped[str | None] = mapped_column(nullable=True)
    sync_cursor: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[str] = mapped_column(default=now)


class GmailOAuthState(Base):
    __tablename__ = "gmail_oauth_states"
    state_hash: Mapped[str] = mapped_column(String(64),primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(36),index=True)
    session_hash: Mapped[str] = mapped_column(String(64))
    verifier_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    expires_at: Mapped[str] = mapped_column(String(40))


class OutreachSettings(Base):
    __tablename__ = "outreach_settings"
    owner_id: Mapped[str] = mapped_column(String(36),primary_key=True)
    data_encrypted: Mapped[bytes] = mapped_column(LargeBinary)


class OutreachContact(Base):
    __tablename__ = "outreach_contacts"
    __table_args__ = (UniqueConstraint("owner_id","email_hash",name="uq_outreach_contact"),)
    id: Mapped[str] = mapped_column(String(36),primary_key=True,default=uid)
    owner_id: Mapped[str] = mapped_column(String(36),index=True)
    email_hash: Mapped[str] = mapped_column(String(64))
    data_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    status: Mapped[str] = mapped_column(String(30),default="active")
    created_at: Mapped[str] = mapped_column(default=now)


class OutreachMessage(Base):
    __tablename__ = "outreach_messages"
    id: Mapped[str] = mapped_column(String(36),primary_key=True,default=uid)
    owner_id: Mapped[str] = mapped_column(String(36),index=True)
    contact_id: Mapped[str] = mapped_column(String(36),index=True)
    parent_id: Mapped[str | None] = mapped_column(String(36),nullable=True)
    status: Mapped[str] = mapped_column(String(30),default="draft",index=True)
    content_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    approval_digest: Mapped[str | None] = mapped_column(String(64),nullable=True)
    approved_at: Mapped[str | None] = mapped_column(nullable=True)
    scheduled_at: Mapped[str | None] = mapped_column(nullable=True,index=True)
    sending_started_at: Mapped[str | None] = mapped_column(nullable=True)
    sent_at: Mapped[str | None] = mapped_column(nullable=True)
    provider_id: Mapped[str | None] = mapped_column(String(255),nullable=True)
    thread_id: Mapped[str | None] = mapped_column(String(255),nullable=True)
    rfc_message_id: Mapped[str] = mapped_column(String(150),default=lambda:f"<{uid()}@internpilot.local>")
    reason: Mapped[str] = mapped_column(String(500),default="Draft awaiting review")
    created_at: Mapped[str] = mapped_column(default=now)
    updated_at: Mapped[str] = mapped_column(default=now)


class OutreachReply(Base):
    __tablename__ = "outreach_replies"
    __table_args__ = (UniqueConstraint("owner_id","provider_id",name="uq_outreach_reply"),)
    id: Mapped[str] = mapped_column(String(36),primary_key=True,default=uid)
    owner_id: Mapped[str] = mapped_column(String(36),index=True)
    contact_id: Mapped[str] = mapped_column(String(36),index=True)
    provider_id: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(30))
    data_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    received_at: Mapped[str] = mapped_column(default=now)


class SchemaVersion(Base):
    __tablename__ = "schema_versions"
    version: Mapped[int] = mapped_column(primary_key=True)
    applied_at: Mapped[str] = mapped_column(default=now)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email_hash: Mapped[str] = mapped_column(String(64), unique=True)
    email_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    password_hash: Mapped[str] = mapped_column(Text)
    profile_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    policy_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    role: Mapped[str] = mapped_column(String(20), default="member", server_default="member")
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_seen_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[str] = mapped_column(default=now)


class LoginSession(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    csrf_token: Mapped[str] = mapped_column(String(100))
    expires_at: Mapped[str] = mapped_column(String(40))


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    slug: Mapped[str] = mapped_column(String(200), default="")
    company: Mapped[str] = mapped_column(String(200))
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    permitted: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    interval_seconds: Mapped[int] = mapped_column(Integer, default=1800)
    last_attempt: Mapped[str | None] = mapped_column(nullable=True)
    last_success: Mapped[str | None] = mapped_column(nullable=True)
    next_run: Mapped[str | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(default="pending")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    cache: Mapped[dict] = mapped_column(JSON, default=dict)
    discovered_count: Mapped[int] = mapped_column(Integer, default=0)


class Opportunity(Base):
    __tablename__ = "opportunities"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    data: Mapped[dict] = mapped_column(JSON)
    first_discovered: Mapped[str] = mapped_column(default=now, index=True)
    last_verified: Mapped[str] = mapped_column(default=now)
    discovery_latency_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)


class SourceOpportunity(Base):
    __tablename__ = "source_opportunities"
    source_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(String(36), primary_key=True)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(String(36), index=True)
    opportunity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    filename: Mapped[str] = mapped_column(String(250))
    kind: Mapped[str] = mapped_column(String(30))
    version: Mapped[int] = mapped_column(Integer, default=1)
    content_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    metadata_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[str] = mapped_column(default=now)


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("owner_id", "opportunity_id", name="uq_candidate_opportunity"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(String(36), index=True)
    opportunity_id: Mapped[str] = mapped_column(String(36), index=True)
    status: Mapped[str] = mapped_column(String(40), default="queued", index=True)
    reason: Mapped[str] = mapped_column(Text, default="Preparation queued")
    document_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    screenshot_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    confirmation_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    confirmation_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    snapshot_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    session_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    approved_at: Mapped[str | None] = mapped_column(nullable=True)
    approval_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    submission_started_at: Mapped[str | None] = mapped_column(nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    preparation_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    submission_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[str] = mapped_column(default=now)
    updated_at: Mapped[str] = mapped_column(default=now)
    upload_approved_at: Mapped[str | None] = mapped_column(nullable=True)
    upload_approval_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    upload_started_at: Mapped[str | None] = mapped_column(nullable=True)


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    dedupe_key: Mapped[str] = mapped_column(String(150), unique=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_owner: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lease_until: Mapped[str | None] = mapped_column(nullable=True)
    available_at: Mapped[str] = mapped_column(default=now)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(default=now)
    updated_at: Mapped[str] = mapped_column(default=now)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(80))
    message: Mapped[str] = mapped_column(Text)
    application_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[str] = mapped_column(default=now, index=True)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(String(36), index=True)
    message: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(50))
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(default=now)
    opportunity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(200), nullable=True, unique=True)


class SavedOpportunity(Base):
    __tablename__ = "saved_opportunities"
    owner_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[str] = mapped_column(default=now)


class NotificationSettings(Base):
    __tablename__ = "notification_settings"
    owner_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    settings_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[str] = mapped_column(default=now)
    updated_at: Mapped[str] = mapped_column(default=now)


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (UniqueConstraint("notification_id", "channel", name="uq_notification_channel"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(String(36), index=True)
    notification_id: Mapped[str] = mapped_column(String(36), index=True)
    channel: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30), default="draft")
    approved_at: Mapped[str | None] = mapped_column(nullable=True)
    not_before: Mapped[str | None] = mapped_column(nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    provider_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[str] = mapped_column(default=now)
    updated_at: Mapped[str] = mapped_column(default=now)


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    last_seen: Mapped[str] = mapped_column(index=True)
    concurrency: Mapped[int] = mapped_column(Integer)
    stopped: Mapped[bool] = mapped_column(Boolean, default=False)


class DeadlineReminder(Base):
    __tablename__ = "deadline_reminders"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(36), index=True)
    opportunity_id: Mapped[str] = mapped_column(String(36))
    deadline_at: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[str] = mapped_column(default=now)


Index("ix_task_claim", Task.status, Task.available_at, Task.priority)
