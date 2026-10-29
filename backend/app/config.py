import os
import json
import base64
import hashlib
from pathlib import Path
from urllib.parse import urlsplit
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)


def database_url(value: str) -> str:
    """Managed providers supply postgres://; use the installed psycopg 3 driver."""
    for prefix in ("postgres://", "postgresql://"):
        if value.startswith(prefix):
            return "postgresql+psycopg://" + value[len(prefix):]
    return value


class Settings:
    data_dir = Path(os.getenv("DATA_DIR", "./data")).resolve()
    data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    database_url = database_url(os.getenv("DATABASE_URL", f"sqlite:///{data_dir / 'internpilot.db'}"))
    database_sslmode = os.getenv("DATABASE_SSLMODE", "")
    encryption_key = os.getenv("ENCRYPTION_KEY", "")
    encryption_secret = os.getenv("ENCRYPTION_SECRET", "")
    if not encryption_key and encryption_secret:
        # Hosting providers generate opaque random strings, not Fernet keys.
        encryption_key = base64.urlsafe_b64encode(hashlib.sha256(encryption_secret.encode()).digest()).decode()
    production = os.getenv("ENVIRONMENT", "development") == "production"
    auto_catalog_backfill = os.getenv("AUTO_CATALOG_BACKFILL", "false" if production else "true").lower() == "true"
    cookie_secure = os.getenv("COOKIE_SECURE", "false").lower() == "true"
    test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
    test_portal_origin = os.getenv("TEST_PORTAL_ORIGIN", "http://127.0.0.1:8000").rstrip("/")
    allow_registration = os.getenv("ALLOW_REGISTRATION", "true").lower() == "true"
    invitation_only = os.getenv("INVITATION_ONLY", "true").lower() == "true"
    registration_token = os.getenv("REGISTRATION_TOKEN", "")
    redis_url = os.getenv("REDIS_URL", "")
    public_origin = (os.getenv("PUBLIC_ORIGIN") or os.getenv("RENDER_EXTERNAL_URL", "")).rstrip("/")
    cors_origins = [s.strip() for s in os.getenv("CORS_ORIGINS", public_origin or "http://localhost:3000,http://127.0.0.1:3000").split(",") if s.strip()]
    worker_heartbeat_file = os.getenv("WORKER_HEARTBEAT_FILE", "")
    concurrency = max(1, min(32, int(os.getenv("WORKER_CONCURRENCY", "2"))))
    browser_concurrency = max(1,min(2,int(os.getenv("BROWSER_CONCURRENCY","1"))))
    worker_kinds = tuple(item.strip() for item in os.getenv("WORKER_KINDS","discovery,application,outreach,gmail_sync").split(",") if item.strip())
    crawl_batch_size = max(10,min(2000,int(os.getenv("CRAWL_BATCH_SIZE","200"))))
    crawl_log_retention_days = max(1,min(90,int(os.getenv("CRAWL_LOG_RETENTION_DAYS","14"))))
    distributed_rate_limits = os.getenv("DISTRIBUTED_RATE_LIMITS","true").lower()=="true"
    llm_daily_request_limit = max(0, int(os.getenv("LLM_DAILY_REQUEST_LIMIT", "200")))
    llm_scan_job_limit = max(0, min(100, int(os.getenv("LLM_SCAN_JOB_LIMIT", "50"))))
    http_host_policies = json.loads(os.getenv("HTTP_HOST_POLICIES", "{}"))
    http_global_concurrency = max(1, min(128, int(os.getenv("HTTP_GLOBAL_CONCURRENCY", "16"))))
    http_host_concurrency = max(1, min(8, int(os.getenv("HTTP_HOST_CONCURRENCY", "2"))))
    http_request_timeout = max(5, min(60, int(os.getenv("HTTP_REQUEST_TIMEOUT", "30"))))
    queue_max_pending = max(10, int(os.getenv("QUEUE_MAX_PENDING", "10000")))
    queue_owner_pending = max(5, int(os.getenv("QUEUE_OWNER_PENDING", "2000")))
    task_max_attempts = max(1, min(10, int(os.getenv("TASK_MAX_ATTEMPTS", "3"))))
    task_lease_seconds = max(60, int(os.getenv("TASK_LEASE_SECONDS", "180")))
    db_pool_size = max(1, min(20, int(os.getenv("DB_POOL_SIZE", "5"))))
    db_max_overflow = max(0, min(20, int(os.getenv("DB_MAX_OVERFLOW", "2"))))
    db_pool_timeout = max(1, int(os.getenv("DB_POOL_TIMEOUT", "15")))
    db_pool_recycle = max(60, int(os.getenv("DB_POOL_RECYCLE", "1800")))
    auth_address_limit = max(1, min(1000, int(os.getenv("AUTH_ADDRESS_LIMIT", "20"))))
    auth_global_limit = max(20, int(os.getenv("AUTH_GLOBAL_LIMIT", "5000")))

    def validate(self):
        if not self.production:
            return
        errors = []
        if not self.database_url.startswith("postgresql+psycopg://"):
            errors.append("production requires PostgreSQL")
        if self.database_sslmode != "verify-full":
            errors.append("production requires DATABASE_SSLMODE=verify-full and a trusted database CA")
        if not self.cookie_secure or self.test_mode:
            errors.append("production requires COOKIE_SECURE=true and TEST_MODE=false")
        if not self.encryption_key or (self.encryption_secret and len(self.encryption_secret) < 32):
            errors.append("a persistent encryption key or random secret of at least 32 characters is required")
        if not self.invitation_only:
            errors.append("production requires INVITATION_ONLY=true")
        for origin in [self.public_origin, *self.cors_origins]:
            parts = urlsplit(origin)
            if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment or parts.path or "*" in origin:
                errors.append("production requires exact HTTPS public and CORS origins")
                break
        if not self.worker_heartbeat_file:
            errors.append("production requires a worker heartbeat file")
        if not self.distributed_rate_limits:
            errors.append("production requires shared source-host rate budgets")
        if not self.worker_kinds or set(self.worker_kinds)-{"discovery","application","outreach","gmail_sync"}:
            errors.append("worker roles must use the documented supported task kinds")
        if errors:
            raise RuntimeError("Unsafe hosting configuration: " + "; ".join(errors))


settings = Settings()
settings.validate()
