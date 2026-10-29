"""Authorized local founder tests. No real identities, messages or infrastructure."""
# ruff: noqa: F811 -- pytest fixtures intentionally imported for injection.
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
import time

import pytest

from test_api_worker import PASSWORD, stack  # noqa: F401
from test_owner_console import owner_account, approval


def code(secret):
    from app.founder_security import totp
    return totp(secret,int(time.time())//30)


def test_totp_rfc6238_sha1_vector():
    from app.founder_security import totp
    assert totp('GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ',1)=='287082'
    assert totp('GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ',1111111109//30)=='081804'


def test_only_one_founder_cli_and_database_enforce_it(stack):
    owner,identifier=owner_account(stack)
    _,member=stack.register('member@example.invalid')
    output=stack.python("from app.admin import main; assert main(['grant-owner','member@example.invalid'])==1")
    assert 'already exists' in output or output==''
    with stack.db() as db:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE users SET role='owner' WHERE id=?",(member['user']['id'],))
        assert db.execute("SELECT count(*) FROM users WHERE role='owner'").fetchone()[0]==1
    assert owner.get('/api/auth/session').json()['user']['id']==identifier


def test_founder_reports_need_reauth_and_never_expose_secrets(stack):
    owner,_=owner_account(stack)
    member,_=stack.register('member@example.invalid')
    for client,status in [(stack.client(),401),(member,403)]:
        assert client.get('/api/owner/report').status_code==status
        assert client.post('/api/owner/unlock',json=approval()).status_code==status
    assert owner.get('/api/owner/report').status_code==403
    assert owner.post('/api/owner/unlock',json=approval(current_password='wrong')).status_code==403
    assert owner.post('/api/owner/unlock',json=approval()).status_code==200
    for section in ['overview','activity','analytics','security','applications','automation','infrastructure','settings']:
        result=owner.get('/api/owner/report',params={'section':section})
        assert result.status_code==200,result.text
        for secret in [PASSWORD,owner.cookies.get('internpilot_session'),owner.headers['X-CSRF-Token']]:
            assert secret not in result.text
    assert any(r['kind']=='owner_report_read' for r in owner.get('/api/owner/audit').json())
    with stack.db() as db:
        db.execute("UPDATE coordination_state SET value=? WHERE key LIKE 'founder-unlock:%'",(json.dumps({'until':'2000'}),))
    assert owner.get('/api/owner/report').status_code==403


def test_failed_login_events_are_durable_and_redacted(stack):
    owner,_=owner_account(stack)
    member,_=stack.register('member@example.invalid')
    assert member.post('/api/auth/login',json={'email':'member@example.invalid','password':'wrong-long-password'}).status_code==401
    owner.post('/api/owner/unlock',json=approval())
    report=owner.get('/api/owner/report?section=security').json()
    failed=[r for r in report['events'] if r['kind']=='login_failed']
    assert failed and failed[0]['email']=='member@example.invalid'
    assert failed[0]['address_tag'] and '127.0.0.1' not in json.dumps(report)
    assert 'wrong-long-password' not in json.dumps(report)


def test_mfa_enrollment_replay_protection_and_no_secret_readback(stack):
    owner,identifier=owner_account(stack)
    assert owner.post('/api/auth/mfa/setup',json={'current_password':'wrong'}).status_code==403
    result=owner.post('/api/auth/mfa/setup',json={'current_password':PASSWORD});assert result.status_code==200
    secret=result.json()['secret']
    assert owner.get('/api/auth/mfa').json()=={'enabled':False}
    assert owner.post('/api/auth/mfa/enable',json={'current_password':PASSWORD,'otp':'bad'}).status_code==403
    assert owner.get('/api/auth/mfa').json()=={'enabled':False}
    assert owner.post('/api/auth/mfa/enable',json={'current_password':PASSWORD,'otp':code(secret)}).status_code==200
    assert secret not in owner.get('/api/auth/mfa').text
    with stack.db() as db:
        assert secret not in '\n'.join(db.iterdump())
        db.execute('UPDATE account_mfa SET last_counter=-1 WHERE user_id=?',(identifier,))
    other=stack.client()
    body={'email':'owner@example.invalid','password':PASSWORD}
    assert other.post('/api/auth/login',json=body).status_code==403
    assert other.post('/api/auth/login',json={**body,'otp':code(secret)}).status_code==200
    assert stack.client().post('/api/auth/login',json={**body,'otp':code(secret)}).status_code==403
    with stack.db() as db:db.execute("UPDATE sessions SET mfa_verified_at='2000' WHERE user_id=?",(identifier,))
    assert owner.post('/api/owner/unlock',json=approval()).status_code==403


def test_forced_recovery_single_use_and_transactional_duplicate_rejection(stack):
    owner,_=owner_account(stack)
    member,account=stack.register('member@example.invalid')
    response=owner.post(f"/api/owner/users/{account['user']['id']}/recovery",json=approval())
    assert response.status_code==200
    token=response.json()['token']
    assert member.get('/api/profile').status_code==401
    assert member.post('/api/auth/login',json={'email':'member@example.invalid','password':PASSWORD}).status_code==403
    with stack.db() as db:assert token not in '\n'.join(db.iterdump())
    credentials={'token':token,'new_password':'synthetic-recovered-password-42!'}
    clients=[stack.client(),stack.client()]
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses=list(pool.map(lambda c:c.post('/api/auth/recover',json=credentials).status_code,clients))
    assert sorted(statuses)==[200,403]
    result=member.post('/api/auth/login',json={'email':'member@example.invalid','password':credentials['new_password']})
    assert result.status_code==200
    member.headers['X-CSRF-Token']=result.json()['csrf_token']
    assert member.get('/api/policy').json()['emergency_stop'] is True


def test_reset_links_expire_locking_is_preserved_and_new_links_invalidate_old(stack):
    owner,founder=owner_account(stack)
    member,account=stack.register('member@example.invalid')
    url=f"/api/owner/users/{account['user']['id']}"
    assert owner.post(f'/api/owner/users/{founder}/recovery',json=approval()).status_code==409
    first=owner.post(url+'/recovery',json=approval()).json()['token']
    second=owner.post(url+'/recovery',json=approval()).json()['token']
    body={'new_password':'synthetic-recovered-password-42!'}
    assert stack.client().post('/api/auth/recover',json={**body,'token':first}).status_code==403
    owner.post(url+'/status',json=approval(disabled=True))
    assert stack.client().post('/api/auth/recover',json={**body,'token':second}).status_code==403
    owner.post(url+'/status',json=approval(disabled=False))
    with stack.db() as db:db.execute("UPDATE password_recoveries SET expires_at='2000'")
    assert stack.client().post('/api/auth/recover',json={**body,'token':second}).status_code==403


def test_explicit_founder_transfer_revokes_prior_admin_sessions(stack):
    owner,_=owner_account(stack)
    _,account=stack.register('member@example.invalid')
    stack.python("from app.admin import main; assert main(['select-founder','member@example.invalid'])==0")
    assert owner.get('/api/auth/session').status_code==401
    with stack.db() as db:
        assert db.execute("SELECT id FROM users WHERE role='owner'").fetchone()[0]==account['user']['id']


def test_migration_refuses_multiple_legacy_owners_until_explicit_selection(stack):
    owner,_=owner_account(stack)
    _,member=stack.register('member@example.invalid')
    with stack.db() as db:
        db.execute('DROP INDEX uq_single_founder')
        db.execute('DELETE FROM schema_versions WHERE version=8')
        db.execute("UPDATE users SET role='owner' WHERE id=?",(member['user']['id'],))
    stack.python("from app.migrate import migrate\ntry:\n migrate()\n raise AssertionError('Migration incorrectly accepted multiple founders')\nexcept RuntimeError as error:\n assert 'Multiple owners' in str(error)")
    stack.python("from app.admin import main; assert main(['select-founder','owner@example.invalid'])==0")
    with stack.db() as db:
        assert db.execute('SELECT max(version) FROM schema_versions').fetchone()[0]==8
        assert db.execute("SELECT count(*) FROM users WHERE role='owner'").fetchone()[0]==1


def test_security_retention_prunes_only_expired_namespaces(stack):
    owner,_=owner_account(stack)
    with stack.db() as db:
        db.execute("INSERT INTO security_events(id,user_id,kind,address_tag,created_at) VALUES('old',NULL,'login_failed','','2000')")
        db.execute("INSERT INTO coordination_state(key,value) VALUES('account-invite:retained','{}')")
        db.execute("INSERT INTO coordination_state(key,value) VALUES('founder-unlock:expired','{\"until\":\"2000\"}')")
    stack.python("from app.database import SessionLocal\nfrom app.security_maintenance import prune\nwith SessionLocal() as db:\n result=prune(db)\n assert result['security_events']==1 and result['coordination_state']==1")
    with stack.db() as db:
        assert db.execute("SELECT count(*) FROM coordination_state WHERE key='account-invite:retained'").fetchone()[0]==1


def test_member_recovery_preserves_mfa_and_sql_parameters_are_hidden(stack):
    owner,_=owner_account(stack)
    member,account=stack.register('member@example.invalid')
    setup=member.post('/api/auth/mfa/setup',json={'current_password':PASSWORD})
    secret=setup.json()['secret']
    assert member.post('/api/auth/mfa/enable',json={'current_password':PASSWORD,'otp':code(secret)}).status_code==200
    token=owner.post(f"/api/owner/users/{account['user']['id']}/recovery",json=approval()).json()['token']
    new='synthetic-recovered-password-42!'
    assert stack.client().post('/api/auth/recover',json={'token':token,'new_password':new}).status_code==200
    assert member.post('/api/auth/login',json={'email':'member@example.invalid','password':new}).status_code==403
    with stack.db() as db:
        assert db.execute('SELECT enabled FROM account_mfa WHERE user_id=?',(account['user']['id'],)).fetchone()[0]
    stack.python('from app.database import engine; assert engine.hide_parameters is True')
