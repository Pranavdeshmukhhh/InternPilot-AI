"""Real local API/SQLite invite admission; no email sends or real recipients."""
# ruff: noqa: F811 -- imported pytest fixture is intentionally injected by name.
from concurrent.futures import ThreadPoolExecutor
import json

import pytest

from test_api_worker import PASSWORD, stack  # noqa: F401
from test_owner_console import approval


@pytest.fixture
def owner(stack):
    stack.python("""
from unittest.mock import patch
from app.admin import main
with patch('getpass.getpass', return_value='synthetic-only-password-2049!'):
    assert main(['create-owner','owner@example.invalid']) == 0
""")
    client = stack.client()
    result = client.post('/api/auth/login',json={'email':'owner@example.invalid','password':PASSWORD})
    assert result.status_code == 200, result.text
    client.headers['X-CSRF-Token'] = result.json()['csrf_token']
    return client


def issue(owner, email='invited@example.invalid'):
    result = owner.post('/api/owner/invitations',json=approval(email=email))
    assert result.status_code == 200, result.text
    return result.json()


@pytest.mark.parametrize('stack',[{'INVITATION_ONLY':'true'}],indirect=True)
def test_invitation_is_email_bound_one_use_and_secrets_are_not_stored(stack,owner):
    invitation = issue(owner)
    client = stack.client()
    credentials = {'email':'invited@example.invalid','password':PASSWORD}
    for token in ['', 'invalid', '☃']:
        assert client.post('/api/auth/register',json={**credentials,'registration_token':token}).status_code == 403
    assert client.post('/api/auth/register',json={'email':'other@example.invalid','password':PASSWORD,'registration_token':invitation['token']}).status_code == 403
    assert client.post('/api/auth/register',json={**credentials,'registration_token':invitation['token']}).status_code == 200
    assert client.post('/api/auth/register',json={**credentials,'registration_token':invitation['token']}).status_code == 403
    listing = owner.get('/api/owner/invitations').json()
    assert listing['items'][0]['status'] == 'used'
    assert invitation['token'] not in json.dumps(listing)
    assert 'token_digest' not in json.dumps(listing)
    with stack.db() as db:
        contents='\n'.join(db.iterdump())
    assert invitation['token'] not in contents and 'invited@example.invalid' not in contents
    assert client.post('/api/auth/login',json=credentials).status_code == 200


@pytest.mark.parametrize('stack',[{'INVITATION_ONLY':'true'}],indirect=True)
def test_invitation_creation_requires_owner_csrf_fresh_password_and_consent(stack,owner):
    assert stack.client().get('/api/owner/invitations').status_code == 401
    for changes in [{'current_password':'wrong'},{'consent':False},{'email':'bad'}]:
        result = owner.post('/api/owner/invitations',json=approval(email='invited@example.invalid',**changes) if 'email' not in changes else approval(**changes))
        assert result.status_code in {403,422}
    csrf=owner.headers.pop('X-CSRF-Token')
    assert owner.post('/api/owner/invitations',json=approval(email='invited@example.invalid')).status_code == 403
    owner.headers['X-CSRF-Token']=csrf
    invitation=issue(owner)
    member=stack.client()
    result=member.post('/api/auth/register',json={'email':'invited@example.invalid','password':PASSWORD,'registration_token':invitation['token']})
    member.headers['X-CSRF-Token']=result.json()['csrf_token']
    assert member.get('/api/owner/invitations').status_code == 403
    assert member.post('/api/owner/invitations',json=approval(email='forged@example.invalid')).status_code == 403


@pytest.mark.parametrize('stack',[{'INVITATION_ONLY':'true'}],indirect=True)
def test_revoked_and_expired_invitations_fail_closed(stack,owner):
    invitation=issue(owner)
    assert owner.post('/api/owner/invitations/'+invitation['id']+'/revoke',json=approval()).status_code == 200
    result=stack.client().post('/api/auth/register',json={'email':'invited@example.invalid','password':PASSWORD,'registration_token':invitation['token']})
    assert result.status_code == 403
    other=issue(owner,'expired@example.invalid')
    with stack.db() as db:
        key='account-invite:'+other['id']
        value=json.loads(db.execute('SELECT value FROM coordination_state WHERE key=?',(key,)).fetchone()[0])
        value['expires_at']='2000-01-01T00:00:00+00:00'
        db.execute('UPDATE coordination_state SET value=? WHERE key=?',(json.dumps(value),key))
    assert stack.client().post('/api/auth/register',json={'email':'expired@example.invalid','password':PASSWORD,'registration_token':other['token']}).status_code == 403


@pytest.mark.parametrize('stack',[{'INVITATION_ONLY':'true'}],indirect=True)
def test_concurrent_redeem_creates_exactly_one_account(stack,owner):
    invitation=issue(owner)
    clients=[stack.client(),stack.client()]
    def redeem(client):
        return client.post('/api/auth/register',json={'email':'invited@example.invalid','password':PASSWORD,'registration_token':invitation['token']}).status_code
    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses=list(executor.map(redeem,clients))
    assert sorted(statuses)==[200,403]
    with stack.db() as db:
        assert db.execute('SELECT count(*) FROM users').fetchone()[0]==2


@pytest.mark.parametrize('stack',[{'INVITATION_ONLY':'true'}],indirect=True)
def test_failed_creation_rolls_back_invitation_consumption(stack,owner):
    invitation=issue(owner)
    with stack.db() as db:
        db.execute("CREATE TRIGGER synthetic_failure BEFORE INSERT ON users BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END;")
    credentials={'email':'invited@example.invalid','password':PASSWORD,'registration_token':invitation['token']}
    assert stack.client().post('/api/auth/register',json=credentials).status_code == 409
    with stack.db() as db:
        db.execute('DROP TRIGGER synthetic_failure')
    assert stack.client().post('/api/auth/register',json=credentials).status_code == 200


@pytest.mark.parametrize('stack',[{'INVITATION_ONLY':'true','REGISTRATION_TOKEN':'shared-legacy-code'}],indirect=True)
def test_shared_code_cannot_bypass_owner_invitation_and_invalid_codes_leave_no_rows(stack,owner):
    assert stack.client().post('/api/auth/register',json={'email':'uninvited@example.invalid','password':PASSWORD,'registration_token':'shared-legacy-code'}).status_code == 403
    with stack.db() as db:
        assert db.execute("SELECT count(*) FROM coordination_state WHERE key LIKE 'account-invite:%'").fetchone()[0]==0
