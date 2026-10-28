"""Account recovery and session revocation against an isolated local API."""
from concurrent.futures import ThreadPoolExecutor
import json
import subprocess
import sys
from threading import Barrier

from test_api_worker import BACKEND, PASSWORD, stack  # noqa: F401 -- pytest fixture registration


NEW_PASSWORD = "synthetic-new-account-password-2050!"


def login(stack, address="candidate@example.invalid", password=PASSWORD):
    client = stack.client()
    response = client.post("/api/auth/login", json={"email": address, "password": password})
    assert response.status_code == 200, response.text
    result = response.json()
    client.headers["X-CSRF-Token"] = result["csrf_token"]
    return client, result


def recover(stack, address, passwords, *, hidden_input=True):
    """Exercise the real CLI entrypoint with synthetic hidden prompt answers."""
    return json.loads(stack.python(f"""
import contextlib, getpass, io, json, warnings
answers = iter({passwords!r})
def password_prompt(*args, **kwargs):
    if not {hidden_input!r}:
        warnings.warn('Hidden password input is unavailable', getpass.GetPassWarning)
    return next(answers)
getpass.getpass = password_prompt
from app.admin import main
output, errors = io.StringIO(), io.StringIO()
with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
    result = main(['reset-password', {address!r}])
print(json.dumps({{'result': result, 'output': output.getvalue(), 'errors': errors.getvalue()}}))
"""))


def test_password_change_rotates_current_session_and_revokes_all_old_sessions(stack):
    current, account = stack.register()
    secondary, _ = login(stack)
    unrelated, _ = stack.register("unrelated@example.invalid")
    old_current = stack.client()
    old_current.cookies.update(current.cookies)
    old_cookie = current.cookies.get("internpilot_session")
    old_csrf = account["csrf_token"]
    with stack.db() as db:
        old_hash = db.execute("SELECT password_hash FROM users WHERE id=?", (account["user"]["id"],)).fetchone()[0]

    response = current.post("/api/auth/password", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["user"] == account["user"]
    assert result["csrf_token"] != old_csrf
    assert current.cookies.get("internpilot_session") != old_cookie
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "samesite=lax" in response.headers["set-cookie"].lower()
    assert old_current.get("/api/auth/session").status_code == 401
    assert secondary.get("/api/auth/session").status_code == 401
    assert unrelated.get("/api/auth/session").status_code == 200
    assert current.get("/api/auth/session").json()["csrf_token"] == result["csrf_token"]
    assert current.post("/api/auth/logout-others", headers={"X-CSRF-Token": old_csrf}).status_code == 403
    current.headers["X-CSRF-Token"] = result["csrf_token"]
    assert current.get("/api/auth/sessions").json()["active_sessions"] == 1
    with stack.db() as db:
        new_hash = db.execute("SELECT password_hash FROM users WHERE id=?", (account["user"]["id"],)).fetchone()[0]
        assert new_hash.startswith("scrypt$") and new_hash != old_hash
        assert db.execute("SELECT count(*) FROM sessions WHERE user_id=?", (account["user"]["id"],)).fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM audit_events WHERE owner_id=? AND kind='password_changed'", (account["user"]["id"],)).fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM notifications WHERE owner_id=? AND kind='password_changed'", (account["user"]["id"],)).fetchone()[0] == 1
        stored = "\n".join(db.iterdump())
        assert PASSWORD not in stored and NEW_PASSWORD not in stored
    assert stack.client().post("/api/auth/login", json={"email": "candidate@example.invalid", "password": PASSWORD}).status_code == 401
    login(stack, password=NEW_PASSWORD)


def test_password_change_requires_current_password_csrf_and_valid_new_password(stack):
    current, account = stack.register()
    with stack.db() as db:
        before = tuple(db.execute("SELECT password_hash FROM users WHERE id=?", (account["user"]["id"],)).fetchone())
    payload = {"current_password": PASSWORD, "new_password": NEW_PASSWORD}
    assert stack.client().post("/api/auth/password", json=payload).status_code == 401
    without_csrf = stack.client()
    without_csrf.cookies.update(current.cookies)
    assert without_csrf.post("/api/auth/password", json=payload).status_code == 403
    current_cookie = current.cookies.get("internpilot_session")
    rejected = current.post("/api/auth/password", json={**payload, "current_password": "wrong-current-secret"})
    assert rejected.status_code == 403
    assert "set-cookie" not in rejected.headers
    assert current.cookies.get("internpilot_session") == current_cookie
    assert current.get("/api/auth/session").json()["csrf_token"] == account["csrf_token"]
    for new_password in ("tiny", "x" * 257, PASSWORD):
        response = current.post("/api/auth/password", json={**payload, "new_password": new_password})
        assert response.status_code == 422, response.text
        assert PASSWORD not in response.text and new_password not in response.text
    assert current.get("/api/auth/session").status_code == 200
    with stack.db() as db:
        assert tuple(db.execute("SELECT password_hash FROM users WHERE id=?", (account["user"]["id"],)).fetchone()) == before
        assert db.execute("SELECT count(*) FROM sessions WHERE user_id=?", (account["user"]["id"],)).fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM audit_events WHERE kind='password_changed'").fetchone()[0] == 0


def test_session_summary_counts_only_active_owned_sessions_and_hides_tokens(stack):
    current, account = stack.register()
    secondary, secondary_account = login(stack)
    expired, expired_account = login(stack)
    unrelated, _ = stack.register("unrelated@example.invalid")
    from hashlib import sha256
    expired_hash = sha256(expired.cookies.get("internpilot_session").encode()).hexdigest()
    with stack.db() as db:
        db.execute("UPDATE sessions SET expires_at='2000-01-01T00:00:00+00:00' WHERE token_hash=?", (expired_hash,))
    response = current.get("/api/auth/sessions")
    assert response.status_code == 200
    summary = response.json()
    assert summary["active_sessions"] == 2
    assert summary["other_sessions"] == 1
    assert summary["current_session_expires_at"]
    assert not any("token" in key.lower() or "cookie" in key.lower() for key in summary)
    for client, result in ((current, account), (secondary, secondary_account), (expired, expired_account)):
        assert client.cookies.get("internpilot_session") not in response.text
        assert result["csrf_token"] not in response.text
    assert unrelated.get("/api/auth/sessions").json()["active_sessions"] == 1
    assert stack.client().get("/api/auth/sessions").status_code == 401


def test_logout_others_preserves_current_session_and_other_accounts(stack):
    current, account = stack.register()
    secondary, _ = login(stack)
    third, _ = login(stack)
    unrelated, _ = stack.register("unrelated@example.invalid")
    current_cookie = current.cookies.get("internpilot_session")
    without_csrf = stack.client()
    without_csrf.cookies.update(current.cookies)
    assert without_csrf.post("/api/auth/logout-others").status_code == 403
    response = current.post("/api/auth/logout-others")
    assert response.status_code == 200, response.text
    assert response.json()["revoked_sessions"] == 2
    assert response.json()["active_sessions"] == 1
    assert current.cookies.get("internpilot_session") == current_cookie
    assert current.get("/api/auth/session").json()["csrf_token"] == account["csrf_token"]
    assert secondary.get("/api/auth/session").status_code == 401
    assert third.get("/api/auth/session").status_code == 401
    assert unrelated.get("/api/auth/session").status_code == 200
    assert current.post("/api/auth/logout-others").json()["revoked_sessions"] == 0
    assert current.get("/api/auth/sessions").json()["other_sessions"] == 0


def test_simultaneous_password_changes_cannot_reuse_a_revoked_session(stack):
    first, _ = stack.register()
    second, _ = login(stack)
    passwords = (NEW_PASSWORD, "synthetic-second-account-password-2051!")
    ready = Barrier(2)

    def change(client, password):
        ready.wait(timeout=10)
        return client.post("/api/auth/password", json={"current_password": PASSWORD, "new_password": password})

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(change, client, password) for client, password in zip((first, second), passwords)]
        responses = [future.result(timeout=30) for future in futures]
    assert sorted(response.status_code for response in responses) == [200, 401]
    winner = next(index for index, response in enumerate(responses) if response.status_code == 200)
    assert (first, second)[winner].get("/api/auth/sessions").json()["active_sessions"] == 1
    assert (first, second)[1 - winner].get("/api/auth/session").status_code == 401
    login(stack, password=passwords[winner])
    assert stack.client().post("/api/auth/login", json={"email": "candidate@example.invalid", "password": passwords[1 - winner]}).status_code == 401


def test_operator_recovery_revokes_sessions_stops_automation_and_records_notice(stack):
    current, account = stack.register()
    secondary, _ = login(stack)
    unrelated, _ = stack.register("unrelated@example.invalid")
    result = recover(stack, "candidate@example.invalid", [NEW_PASSWORD, NEW_PASSWORD])
    assert result["result"] == 0, result
    assert NEW_PASSWORD not in result["output"] + result["errors"]
    assert current.get("/api/auth/session").status_code == 401
    assert secondary.get("/api/auth/session").status_code == 401
    assert unrelated.get("/api/auth/session").status_code == 200
    with stack.db() as db:
        assert db.execute("SELECT count(*) FROM sessions WHERE user_id=?", (account["user"]["id"],)).fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM audit_events WHERE owner_id=? AND kind='password_reset'", (account["user"]["id"],)).fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM notifications WHERE owner_id=? AND kind='password_reset'", (account["user"]["id"],)).fetchone()[0] == 1
        stored = "\n".join(db.iterdump())
        assert NEW_PASSWORD not in stored and PASSWORD not in stored
    restored, _ = login(stack, password=NEW_PASSWORD)
    assert restored.get("/api/policy").json()["emergency_stop"] is True
    assert restored.post("/api/discovery/run").status_code == 409
    assert stack.client().post("/api/auth/login", json={"email": "candidate@example.invalid", "password": PASSWORD}).status_code == 401


def test_operator_recovery_refuses_invalid_confirmation_or_visible_password_input(stack):
    current, account = stack.register()
    with stack.db() as db:
        old_hash = db.execute("SELECT password_hash FROM users WHERE id=?", (account["user"]["id"],)).fetchone()[0]
    for passwords, hidden in (([NEW_PASSWORD, "synthetic-mismatch-secret"], True), (["tiny", "tiny"], True), (["x" * 257, "x" * 257], True), ([NEW_PASSWORD, NEW_PASSWORD], False)):
        result = recover(stack, "candidate@example.invalid", passwords, hidden_input=hidden)
        assert result["result"] == 1, result
        output = result["output"] + result["errors"]
        assert not any(password in output for password in passwords)
    assert current.get("/api/auth/session").status_code == 200
    assert current.get("/api/policy").json()["emergency_stop"] is False
    with stack.db() as db:
        assert db.execute("SELECT password_hash FROM users WHERE id=?", (account["user"]["id"],)).fetchone()[0] == old_hash
        assert db.execute("SELECT count(*) FROM audit_events WHERE kind='password_reset'").fetchone()[0] == 0


def test_operator_cli_rejects_password_arguments_without_echoing_them(stack):
    current, _ = stack.register()
    result = subprocess.run(
        [sys.executable, "-m", "app.admin", "reset-password", "candidate@example.invalid", "--password", NEW_PASSWORD],
        cwd=BACKEND, env=stack.env, text=True, capture_output=True, timeout=15,
    )
    assert result.returncode != 0
    assert NEW_PASSWORD not in result.stdout + result.stderr
    assert current.get("/api/auth/session").status_code == 200
