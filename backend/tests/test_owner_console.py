"""Owner authority is explicit; credentials never become readable records."""
import json

from test_api_worker import PASSWORD, stack  # noqa: F401 -- pytest fixture registration


def owner_account(stack):
    client,account = stack.register("owner@example.invalid")
    output = stack.python("from app.admin import main; assert main(['grant-owner','owner@example.invalid'])==0")
    assert PASSWORD not in output
    assert client.get("/api/auth/session").status_code == 401
    response = client.post("/api/auth/login",json={"email":"owner@example.invalid","password":PASSWORD})
    assert response.status_code == 200,response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    assert response.json()["user"]["role"] == "owner"
    return client,account["user"]["id"]


def approval(**changes):
    return {"current_password":PASSWORD,"purpose":"Synthetic authorized support request","consent":True,**changes}


def test_members_and_anonymous_cannot_read_owner_data_or_claim_owner_role(stack):
    member,_ = stack.register()
    assert member.get("/api/auth/session").json()["user"]["role"] == "member"
    for endpoint in ("overview","users","audit"):
        assert stack.client().get("/api/owner/"+endpoint).status_code == 401
        assert member.get("/api/owner/"+endpoint).status_code == 403
    assert member.post("/api/owner/users/any/inspect",json=approval()).status_code == 403
    assert member.put("/api/profile",json={**member.get('/api/profile').json(),"role":"owner"}).status_code == 422
    assert stack.client().post('/api/auth/register',json={"email":"forged@example.invalid","password":PASSWORD,"role":"owner"}).status_code == 422


def test_owner_directory_and_presence_are_real_without_credential_material(stack):
    owner,owner_id = owner_account(stack)
    member,account = stack.register("member@example.invalid")
    listing = owner.get("/api/owner/users").json()
    assert listing["total"] == 2
    data = next(row for row in listing["items"] if row["id"] == account["user"]["id"])
    assert data["email"] == "member@example.invalid" and data["last_login_at"] and data["last_seen_at"]
    assert set(data) == {"id","email","role","disabled","created_at","last_login_at","last_seen_at"}
    assert owner.get("/api/owner/users?search=member%40").json()["total"] == 1
    assert owner.get("/api/owner/users?page_size=1&page=2").json()["items"][0]["id"] != listing["items"][0]["id"]
    summary = owner.get("/api/owner/overview").json()
    assert summary["tables"]["users"] == 2 and summary["active_sessions"] == 2
    assert member.get('/api/profile').status_code == 200
    assert any(row["kind"] == "owner_directory_read" for row in owner.get("/api/owner/audit").json())
    with stack.db() as db:
        hashes = [row[0] for row in db.execute('SELECT password_hash FROM users')]
    for secret in [PASSWORD,*hashes,owner.cookies.get('internpilot_session'),owner.headers['X-CSRF-Token']]:
        assert secret not in json.dumps(listing)
        assert secret not in json.dumps(summary)


def test_sensitive_records_require_current_password_consent_reason_and_csrf(stack):
    owner,_ = owner_account(stack)
    member,account = stack.register('member@example.invalid')
    user_id = account['user']['id']
    endpoint = f'/api/owner/users/{user_id}/inspect'
    assert owner.post(endpoint,json=approval(current_password='wrong-password')).status_code == 403
    assert owner.post(endpoint,json=approval(consent=False)).status_code == 422
    assert owner.post(endpoint,json=approval(purpose='short')).status_code == 422
    assert owner.post(endpoint,json=approval(purpose='Support reason '+PASSWORD)).status_code == 422
    without_csrf = stack.client();without_csrf.cookies.update(owner.cookies)
    assert without_csrf.post(endpoint,json=approval()).status_code == 403
    profile = member.get('/api/profile').json()
    profile.update(name='Synthetic private candidate',verified_answers={'private secret question':{'value':'synthetic-vault-value'}})
    assert member.put('/api/profile',json=profile).status_code == 200
    response = owner.post(endpoint,json=approval())
    assert response.status_code == 200,response.text
    assert response.json()['profile']['name'] == 'Synthetic private candidate'
    assert 'verified_answers' not in response.json()['profile'] and 'synthetic-vault-value' not in response.text
    assert member.get('/api/notifications').json()[0]['kind'] == 'owner_account_access'
    audit = owner.get('/api/owner/audit').json()
    assert any(row['kind']=='owner_records_inspected' and user_id in row['message'] for row in audit)
    assert PASSWORD not in json.dumps(audit)


def test_owner_document_download_is_exact_scoped_and_audited(stack):
    owner,_ = owner_account(stack)
    member,account = stack.register('member@example.invalid')
    uploaded = member.post('/api/documents/upload',files={'file':('resume.txt',b'Synthetic private resume only','text/plain')}).json()
    user_id = account['user']['id']
    endpoint = f'/api/owner/users/{user_id}/documents/{uploaded["id"]}/download'
    assert member.post(endpoint,json=approval()).status_code == 403
    assert owner.post(endpoint,json=approval(current_password='wrong')).status_code == 403
    response = owner.post(endpoint,json=approval())
    assert response.status_code == 200 and response.content == b'Synthetic private resume only'
    assert 'attachment' in response.headers['content-disposition']
    assert owner.post(f'/api/owner/users/missing/documents/{uploaded["id"]}/download',json=approval()).status_code == 404
    assert any(row['kind']=='owner_document_downloaded' for row in owner.get('/api/owner/audit').json())


def test_disabling_member_revokes_sessions_pauses_workers_and_keeps_owner_enabled(stack):
    owner,owner_id = owner_account(stack)
    member,account = stack.register('member@example.invalid')
    user_id = account['user']['id']
    result = owner.post(f'/api/owner/users/{user_id}/status',json=approval(disabled=True))
    assert result.status_code == 200 and result.json()['revoked_sessions'] == 1
    assert member.get('/api/profile').status_code == 401
    assert member.post('/api/auth/login',json={'email':'member@example.invalid','password':PASSWORD}).status_code == 403
    assert owner.post(f'/api/owner/users/{owner_id}/status',json=approval(disabled=True)).status_code == 409
    stack.python('from app.worker import schedule_due; schedule_due()')
    with stack.db() as db:
        assert db.execute('SELECT count(*) FROM tasks WHERE owner_id=?',(user_id,)).fetchone()[0] == 0
    assert owner.post(f'/api/owner/users/{user_id}/status',json=approval(disabled=False)).status_code == 200
    response = member.post('/api/auth/login',json={'email':'member@example.invalid','password':PASSWORD})
    assert response.status_code == 200
    member.headers['X-CSRF-Token'] = response.json()['csrf_token']
    assert member.get('/api/policy').json()['emergency_stop'] is True


def test_owner_can_reset_but_never_retrieve_a_password(stack):
    owner,_ = owner_account(stack)
    member,account = stack.register('member@example.invalid')
    user_id = account['user']['id']
    new_password = 'synthetic-replacement-password-2049!'
    response = owner.post(f'/api/owner/users/{user_id}/password',json=approval(new_password=new_password))
    assert response.status_code == 200,response.text
    assert new_password not in response.text and PASSWORD not in response.text
    assert member.get('/api/profile').status_code == 401
    assert member.post('/api/auth/login',json={'email':'member@example.invalid','password':PASSWORD}).status_code == 401
    assert member.post('/api/auth/login',json={'email':'member@example.invalid','password':new_password}).status_code == 200
    assert owner.get(f'/api/owner/users/{user_id}/password').status_code == 405
    with stack.db() as db:
        data='\n'.join(db.iterdump())
        assert PASSWORD not in data and new_password not in data
        assert db.execute('SELECT password_hash FROM users WHERE id=?',(user_id,)).fetchone()[0].startswith('scrypt$')


def test_owner_session_revocation_requires_reauthentication(stack):
    owner,_ = owner_account(stack)
    member,account = stack.register('member@example.invalid')
    endpoint = f'/api/owner/users/{account["user"]["id"]}/sessions/revoke'
    assert owner.post(endpoint,json=approval()).json()['revoked_sessions'] == 1
    assert member.get('/api/auth/session').status_code == 401


def test_named_owner_bootstrap_uses_hidden_password_and_does_not_overwrite_accounts(stack):
    result = stack.python('''
import getpass
from app.admin import main
values=iter(['synthetic-owner-new-password-2049!']*2)
getpass.getpass=lambda prompt: next(values)
assert main(['create-owner','named-owner@example.invalid'])==0
''')
    assert 'synthetic-owner-new-password-2049!' not in result
    client = stack.client()
    response = client.post('/api/auth/login',json={'email':'named-owner@example.invalid','password':'synthetic-owner-new-password-2049!'})
    assert response.status_code == 200 and response.json()['user']['role'] == 'owner'
    assert client.post('/api/auth/register',json={'email':'named-owner@example.invalid','password':PASSWORD}).status_code == 409


def test_version_three_migration_defaults_every_existing_account_to_member(stack):
    member,_ = stack.register()
    with stack.db() as db:
        db.execute('DELETE FROM schema_versions WHERE version=4')
        for name in ('role','disabled','last_login_at','last_seen_at'):
            db.execute(f'ALTER TABLE users DROP COLUMN {name}')
    stack.python('from app.migrate import migrate; migrate();migrate()')
    assert member.get('/api/auth/session').json()['user']['role'] == 'member'
    with stack.db() as db:
        assert [row[0] for row in db.execute('SELECT version FROM schema_versions ORDER BY version')] == [1,2,3,4,5,6,7]


def test_worker_controls_require_owner_action_and_preserve_tenant_diagnostics(stack):
    owner,_=owner_account(stack)
    member,_=stack.register('controls-member@example.invalid')
    assert member.get('/api/owner/workers/control').status_code==403
    assert owner.post('/api/owner/workers/control',json=approval(paused=True,consent=False)).status_code==422
    response=owner.post('/api/owner/workers/control',json=approval(paused=True,paused_kinds=['discovery']))
    assert response.status_code==200,response.text
    assert owner.get('/api/dashboard').json()['worker']['control']['paused'] is True
    sources=owner.get('/api/sources').json()
    source_id=sources[0]['id']
    assert owner.get(f'/api/sources/{source_id}/diagnostics').status_code==200
    assert member.get(f'/api/sources/{source_id}/diagnostics').status_code==404
    assert owner.post('/api/owner/workers/control',json=approval(paused=False)).status_code==200
