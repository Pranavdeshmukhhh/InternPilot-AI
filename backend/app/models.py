from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import String, Text, Integer, Boolean, LargeBinary, JSON, UniqueConstraint, Index, Float, ForeignKey, DateTime, case, select, type_coerce, event, and_, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.ext.hybrid import hybrid_property
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
    __table_args__ = (Index("uq_single_founder","role",unique=True,sqlite_where=text("role='owner'"),postgresql_where=text("role='owner'")),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email_hash: Mapped[str] = mapped_column(String(64), unique=True)
    email_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    password_hash: Mapped[str] = mapped_column(Text)
    profile_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    policy_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    role: Mapped[str] = mapped_column(String(20), default="member", server_default="member")
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    reset_required: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    security_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_login_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_seen_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[str] = mapped_column(default=now)


class LoginSession(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    csrf_token: Mapped[str] = mapped_column(String(100))
    expires_at: Mapped[str] = mapped_column(String(40))
    mfa_verified_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class AccountMFA(Base):
    __tablename__ = "account_mfa"
    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    secret_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_counter: Mapped[int] = mapped_column(Integer, default=-1)
    created_at: Mapped[str] = mapped_column(default=now)


class PasswordRecovery(Base):
    __tablename__ = "password_recoveries"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    security_version: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[str] = mapped_column(String(40), index=True)
    used_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class SecurityEvent(Base):
    __tablename__ = "security_events"
    __table_args__ = (Index("ix_security_user_time", "user_id", "created_at"), Index("ix_security_kind_time", "kind", "created_at"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    kind: Mapped[str] = mapped_column(String(40))
    address_tag: Mapped[str] = mapped_column(String(24), default="")
    created_at: Mapped[str] = mapped_column(String(40), default=now)


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
    scan_generation: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class Opportunity(Base):
    __tablename__ = "opportunities"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    # Historical IDs remain valid aliases. Only canonical rows store fact payloads.
    # Keeping the physical `data` column preserves old inserts and v5 recovery.
    _payload: Mapped[dict] = mapped_column("data", JSON)
    canonical_id: Mapped[str | None] = mapped_column(ForeignKey("opportunities.id"), nullable=True, index=True)
    canonical: Mapped["Opportunity | None"] = relationship(remote_side="Opportunity.id", lazy="joined", join_depth=1)
    catalog_scope: Mapped[str] = mapped_column(String(100), default="legacy", server_default="legacy")
    projection_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    authority_rank: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    kind: Mapped[str | None] = mapped_column(String(30), nullable=True)
    company_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_document: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    url_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    remote_flag: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    active_flag: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sort_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_discovered: Mapped[str] = mapped_column(default=now, index=True)
    last_verified: Mapped[str] = mapped_column(default=now)
    discovery_latency_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    @hybrid_property
    def data(self):
        return self.canonical._payload if self.canonical_id and self.canonical else self._payload

    @data.inplace.setter
    def _set_data(self, value):
        # Legacy/private mutation never writes through into a public record.
        if self.canonical_id:
            self.canonical_id = None
            self.canonical = None
        self._payload = value

    @data.inplace.expression
    @classmethod
    def _data_expression(cls):
        canonical = cls.__table__.alias("canonical_facts")
        payload = select(canonical.c.data).where(canonical.c.id == cls.canonical_id).correlate(cls).scalar_subquery()
        return type_coerce(case((cls.canonical_id.is_not(None), payload), else_=cls._payload), JSON)


class CatalogSource(Base):
    """Operator-reviewed public source; user Source rows remain subscriptions."""
    __tablename__ = "catalog_sources"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    config: Mapped[dict] = mapped_column(JSON)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    cache: Mapped[dict] = mapped_column(JSON, default=dict)
    generation: Mapped[int] = mapped_column(Integer, default=0)
    lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_until: Mapped[str | None] = mapped_column(nullable=True)
    last_success: Mapped[str | None] = mapped_column(nullable=True)


class CatalogListing(Base):
    __tablename__ = "catalog_listings"
    source_id: Mapped[str] = mapped_column(ForeignKey("catalog_sources.id"), primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), primary_key=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    verified: Mapped[bool] = mapped_column(Boolean, default=True)


class OpportunityArchive(Base):
    """Private encrypted pre-consolidation snapshot; never part of public facts."""
    __tablename__ = "opportunity_archives"
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(36), index=True)
    payload_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    archived_at: Mapped[str] = mapped_column(default=now)


@event.listens_for(Opportunity, "before_insert")
@event.listens_for(Opportunity, "before_update")
def project_opportunity(mapper, connection, target):
    if not target.canonical_id:
        from .catalog_projection import projection
        target.first_discovered = target.first_discovered or now()
        for key, value in projection(target._payload or {}, target.first_discovered).items():
            setattr(target, key, value)


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
Index("ix_catalog_newest", Opportunity.projection_version, Opportunity.canonical_id, Opportunity.kind, Opportunity.sort_at.desc(), Opportunity.id.desc())
Index("ix_catalog_deadline", Opportunity.projection_version, Opportunity.canonical_id, Opportunity.kind, Opportunity.deadline_at, Opportunity.id)
Index("ix_catalog_unprojected", Opportunity.id,
    postgresql_where=and_(Opportunity.canonical_id.is_(None), Opportunity.projection_version != 1),
    sqlite_where=and_(Opportunity.canonical_id.is_(None), Opportunity.projection_version != 1))
Index("ix_source_opportunity_reverse", SourceOpportunity.opportunity_id, SourceOpportunity.source_id)
Index("ix_application_owner_created", Application.owner_id, Application.created_at, Application.id)
Index("ix_saved_owner_created", SavedOpportunity.owner_id, SavedOpportunity.created_at, SavedOpportunity.opportunity_id)


class CoordinationState(Base):
    __tablename__ = "coordination_state"
    key: Mapped[str] = mapped_column(String(160), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)


class RequestLease(Base):
    __tablename__ = "request_leases"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    host: Mapped[str] = mapped_column(String(253), index=True)
    expires_at: Mapped[str] = mapped_column(String(40), index=True)


class DiscoveryHealth(Base):
    __tablename__ = "discovery_health"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    failures: Mapped[int] = mapped_column(default=0)
    next_attempt: Mapped[str | None] = mapped_column(nullable=True)
    last_checked: Mapped[str | None] = mapped_column(nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(100), nullable=True)
    checkpoint: Mapped[dict] = mapped_column(JSON, default=dict)
