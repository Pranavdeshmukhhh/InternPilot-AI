"""Hosted sign-in, safe production configuration and process failure behavior."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest
from cryptography.fernet import Fernet
from test_api_worker import stack, PASSWORD  # noqa: F401 -- pytest fixture registration

ROOT = Path(__file__).resolve().parents[2]
INVITE = "synthetic-invitation-only-abcdefghijklmnopqrstuvwxyz"


@pytest.mark.parametrize("stack", [{"REGISTRATION_TOKEN": INVITE}], indirect=True)
def test_hosted_invitation_protects_account_creation_and_is_not_stored(stack):
    client = stack.client()
    health = client.get("/api/health")
    assert health.json()["registration_requires_invite"] is True
    assert INVITE not in health.text
    credentials = {"email": "invited@example.invalid", "password": PASSWORD}
    for token in ("", "incorrect", "☃"):
        response = client.post("/api/auth/register", json={**credentials, "registration_token": token})
        assert response.status_code == 403
        assert INVITE not in response.text
    assert client.post("/api/auth/register", json={**credentials, "registration_token": INVITE}).status_code == 200
    assert client.post("/api/auth/login", json=credentials).status_code == 200
    with stack.db() as db:
        assert db.execute("SELECT count(*) FROM users").fetchone()[0] == 1
        assert INVITE not in "\n".join(db.iterdump())


@pytest.mark.parametrize("stack", [{"ALLOW_REGISTRATION": "false", "REGISTRATION_TOKEN": INVITE}], indirect=True)
def test_operator_can_close_registration(stack):
    client = stack.client()
    assert client.get("/api/health").json()["allow_registration"] is False
    assert client.post("/api/auth/register", json={"email": "closed@example.invalid", "password": PASSWORD, "registration_token": INVITE}).status_code == 403


@pytest.mark.parametrize("stack", [{"WORKER_HEARTBEAT_FILE": "{data_dir}/heartbeat"}], indirect=True)
def test_readiness_observes_worker_progress(stack):
    # Use the real HTTP API, but never execute an external application.
    heartbeat = stack.directory / "heartbeat"
    client = stack.client()
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/ready").status_code == 503
    heartbeat.touch()
    assert client.get("/api/ready").status_code == 200
    stale = time.time() - 100
    os.utime(heartbeat, (stale, stale))
    assert client.get("/api/ready").status_code == 503


def configuration(tmp_path, changes=None):
    env = {**os.environ, "DATA_DIR": str(tmp_path), "ENVIRONMENT": "production",
           "DATABASE_URL": "postgres://user:synthetic%40password@db.example.invalid/internpilot",
           "DATABASE_SSLMODE": "verify-full", "ENCRYPTION_KEY": "",
           "ENCRYPTION_SECRET": "synthetic-encryption-material-0123456789",
           "COOKIE_SECURE": "true", "TEST_MODE": "false", "ALLOW_REGISTRATION": "true",
           "REGISTRATION_TOKEN": INVITE, "INVITATION_ONLY":"true", "PUBLIC_ORIGIN": "https://app.example.invalid",
           "CORS_ORIGINS": "https://app.example.invalid", "WORKER_HEARTBEAT_FILE": str(tmp_path / "heartbeat")}
    env.update(changes or {})
    return subprocess.run([sys.executable, "-c", "from app.config import settings; print(settings.database_url.split(':')[0]); print(len(settings.encryption_key))"],
                          cwd=ROOT / "backend", env=env, text=True, capture_output=True)


@pytest.mark.parametrize("prefix", ["postgres://", "postgresql://", "postgresql+psycopg://"])
def test_managed_postgres_urls_use_psycopg3(tmp_path, prefix):
    result = configuration(tmp_path, {"DATABASE_URL": prefix + "u:p@db.invalid/db"})
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["postgresql+psycopg", "44"]


@pytest.mark.parametrize("changes", [
    {"DATABASE_URL": "sqlite:///data.db"}, {"DATABASE_SSLMODE": "disable"},
    {"DATABASE_SSLMODE":"require"}, {"DATABASE_SSLMODE":"verify-ca"},
    {"COOKIE_SECURE": "false"}, {"TEST_MODE": "true"},
    {"ENCRYPTION_SECRET": ""}, {"ENCRYPTION_SECRET": "short"},
    {"INVITATION_ONLY": "false"},
    {"PUBLIC_ORIGIN": "http://app.example.invalid"}, {"PUBLIC_ORIGIN": "https://app.example.invalid/path"},
    {"PUBLIC_ORIGIN": "https://user:password@app.example.invalid"},
    {"CORS_ORIGINS": "*"}, {"WORKER_HEARTBEAT_FILE": ""},
])
def test_unsafe_cloud_configuration_fails_before_serving(tmp_path, changes):
    result = configuration(tmp_path, changes)
    assert result.returncode != 0
    assert "Unsafe hosting configuration" in result.stderr
    assert INVITE not in result.stderr
    assert "synthetic-encryption-material" not in result.stderr


def hosted_module():
    spec = importlib.util.spec_from_file_location("hosted_start", ROOT / "deploy/start.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_replacing_cloud_secret_cannot_silently_replace_encryption_key(tmp_path):
    runtime = hosted_module()
    cipher = Fernet(Fernet.generate_key())
    runtime.check_storage_key(tmp_path, cipher)
    original = (tmp_path / "storage-key-check").read_bytes()
    runtime.check_storage_key(tmp_path, cipher)
    assert (tmp_path / "storage-key-check").read_bytes() == original
    with pytest.raises(RuntimeError, match="Restore the original"):
        runtime.check_storage_key(tmp_path, Fernet(Fernet.generate_key()))
    assert (tmp_path / "storage-key-check").read_bytes() == original


@pytest.mark.skipif(os.name == "nt", reason="Hosted container supervisor runs on Linux")
def test_failed_child_stops_other_services(tmp_path):
    pid_file = tmp_path / "child.pid"
    child_script = "import os,time,pathlib; pathlib.Path(os.environ['PID_FILE']).write_text(str(os.getpid())); time.sleep(30)"
    env = {**os.environ, "PID_FILE": str(pid_file)}
    commands = [
        ("sibling", [sys.executable, "-c", child_script], tmp_path, env),
        ("failing", [sys.executable, "-c", "import time; time.sleep(0.7); raise SystemExit(7)"], tmp_path, env),
    ]
    assert hosted_module().supervise(commands, tmp_path / "heartbeat", grace_seconds=2) == 1
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)
