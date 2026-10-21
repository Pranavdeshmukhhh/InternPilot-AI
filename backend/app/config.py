import os
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
    cookie_secure = os.getenv("COOKIE_SECURE", "false").lower() == "true"
    test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
    test_portal_origin = os.getenv("TEST_PORTAL_ORIGIN", "http://127.0.0.1:8000").rstrip("/")
    allow_registration = os.getenv("ALLOW_REGISTRATION", "true").lower() == "true"
    registration_token = os.getenv("REGISTRATION_TOKEN", "")
    redis_url = os.getenv("REDIS_URL", "")
    public_origin = (os.getenv("PUBLIC_ORIGIN") or os.getenv("RENDER_EXTERNAL_URL", "")).rstrip("/")
    cors_origins = [s.strip() for s in os.getenv("CORS_ORIGINS", public_origin or "http://localhost:3000,http://127.0.0.1:3000").split(",") if s.strip()]
    worker_heartbeat_file = os.getenv("WORKER_HEARTBEAT_FILE", "")
    concurrency = max(1, min(4, int(os.getenv("WORKER_CONCURRENCY", "2"))))
    task_lease_seconds = max(60, int(os.getenv("TASK_LEASE_SECONDS", "180")))

    def validate(self):
        if not self.production:
            return
        errors = []
        if not self.database_url.startswith("postgresql+psycopg://"):
            errors.append("production requires PostgreSQL")
        if self.database_sslmode not in {"require", "verify-ca", "verify-full"}:
            errors.append("production requires encrypted PostgreSQL transport")
        if not self.cookie_secure or self.test_mode:
            errors.append("production requires COOKIE_SECURE=true and TEST_MODE=false")
        if not self.encryption_key or (self.encryption_secret and len(self.encryption_secret) < 32):
            errors.append("a persistent encryption key or random secret of at least 32 characters is required")
        if self.allow_registration and len(self.registration_token) < 32:
            errors.append("production registration requires an invitation token of at least 32 characters")
        for origin in [self.public_origin, *self.cors_origins]:
            parts = urlsplit(origin)
            if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment or parts.path or "*" in origin:
                errors.append("production requires exact HTTPS public and CORS origins")
                break
        if not self.worker_heartbeat_file:
            errors.append("production requires a worker heartbeat file")
        if errors:
            raise RuntimeError("Unsafe hosting configuration: " + "; ".join(errors))


settings = Settings()
settings.validate()
