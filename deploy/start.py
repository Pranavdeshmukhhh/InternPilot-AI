"""Run the complete application on a single persistent cloud service.

The host supplies HTTPS and restarts this process on failure. Children run as an
unprivileged user, share encrypted storage, and stop together on any failure.
"""
from __future__ import annotations

import os
import pwd
import signal
import subprocess
import sys
import time
from pathlib import Path


def drop_privileges():
    directory = Path(os.environ.get("DATA_DIR", "/data/internpilot"))
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.getuid() == 0:
        # Only the application subdirectory is owned by the application. Do not
        # recursively change unrelated files or the provider's disk mount.
        os.chown(directory, 10001, 10001)
        os.chmod(directory, 0o700)
        os.setgroups([])
        os.setgid(10001)
        os.setuid(10001)
    # Keep HOME pointing at the effective user's actual login directory. libpq
    # and Chromium must not try to read the root account's TLS/cache files.
    os.environ["HOME"] = pwd.getpwuid(os.getuid()).pw_dir
    os.umask(0o077)


def check_storage_key(directory: Path, cipher):
    """Fail closed if an operator accidentally replaces a persistent secret."""
    marker = directory / "storage-key-check"
    expected = b"InternPilot storage key v1"
    try:
        fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        try:
            if cipher.decrypt(marker.read_bytes()) != expected:
                raise ValueError("Unexpected storage marker")
        except Exception:
            raise RuntimeError("Storage encryption key changed. Restore the original hosting secret before restarting.") from None
    else:
        with os.fdopen(fd, "wb") as stream:
            stream.write(cipher.encrypt(expected))
            stream.flush()
            os.fsync(stream.fileno())


def supervise(commands, heartbeat: Path, *, grace_seconds=25):
    stopped = False
    children = []
    previous_handlers = {}

    def stop(_signum, _frame):
        nonlocal stopped
        stopped = True

    for sig in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[sig] = signal.signal(sig, stop)
    try:
        for name, command, directory, child_env in commands:
            process = subprocess.Popen(command, cwd=directory, env=child_env, start_new_session=True)
            children.append((name, process))
            print(f"Started {name}.", flush=True)
        started = time.monotonic()
        while not stopped:
            for name, process in children:
                if process.poll() is not None:
                    print(f"{name} exited; restarting the complete service is required.", flush=True)
                    return 1
            if time.monotonic() - started > 90:
                try:
                    age = time.time() - heartbeat.stat().st_mtime
                except OSError:
                    age = 999
                if age < 0 or age > 60:
                    print("Worker heartbeat is stale; restarting the complete service is required.", flush=True)
                    return 1
            time.sleep(0.5)
        return 0
    finally:
        for _, process in children:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + grace_seconds
        for _, process in children:
            try:
                process.wait(timeout=max(0.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                pass
        # Also clean up browser descendants that outlive a stopped worker.
        for _, process in children:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)


def main():
    drop_privileges()
    sys.path.insert(0, "/app/backend")
    from app.config import settings
    from app.security import fernet
    from app.migrate import migrate

    check_storage_key(settings.data_dir, fernet)
    migrate()
    heartbeat = Path(settings.worker_heartbeat_file)
    if not settings.worker_heartbeat_file:
        raise RuntimeError("WORKER_HEARTBEAT_FILE is required for the hosted supervisor")
    heartbeat.unlink(missing_ok=True)
    common = {**os.environ, "PYTHONUNBUFFERED": "1"}
    frontend = {**common, "HOSTNAME": "0.0.0.0", "PORT": os.getenv("PORT", "10000")}
    commands = [
        ("API", [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000", "--no-proxy-headers"], "/app/backend", common),
        ("worker", [sys.executable, "-m", "app.worker"], "/app/backend", common),
        ("frontend", ["node", "server.js"], "/app/frontend", frontend),
    ]
    return supervise(commands, heartbeat)


if __name__ == "__main__":
    raise SystemExit(main())
