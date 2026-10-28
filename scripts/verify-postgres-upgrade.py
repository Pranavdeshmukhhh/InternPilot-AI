"""Verify migrations/parallel claims in a fresh scratch DB on a local test container.

The existing database is not modified. A random role/database are created and
removed; credentials travel through stdin/environment and are never printed.
"""
import argparse
import json
import os
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet
from psycopg import sql
from sqlalchemy.engine import URL

ROOT=Path(__file__).resolve().parents[1]
PROGRAM='''
import json,time
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select,text,update
from app.migrate import migrate
from app.database import SessionLocal,engine
from app.models import User,Source,Task,SchemaVersion
from app.schemas import Profile,Policy
from app.security import encrypt,decrypt,digest
from app.worker import schedule_due,claim_task
from app.rate_limits import reserve
migrate()
with SessionLocal() as db:
 user=User(email_hash=digest('postgres-synthetic@example.invalid'),email_encrypted=encrypt('postgres-synthetic@example.invalid'),password_hash='synthetic-unused',profile_encrypted=encrypt(Profile().model_dump()),policy_encrypted=encrypt(Policy().model_dump()))
 db.add(user);db.flush();owner=user.id
 db.add_all([Source(owner_id=owner,kind='greenhouse',slug=f'synthetic-{i}',company='SYNTHETIC PostgreSQL benchmark',permitted=True,enabled=True) for i in range(1000)])
 db.commit()
with engine.begin() as c:
 c.execute(text('DELETE FROM schema_versions WHERE version=5'))
 for table in ('gmail_connections','gmail_oauth_states','outreach_settings','outreach_contacts','outreach_messages','outreach_replies','crawl_runs','host_budgets'):
  c.execute(text('DROP TABLE '+table))
migrate();migrate()
with SessionLocal() as db:
 assert decrypt(db.get(User,owner).profile_encrypted)['graduation_year']==2029
 versions=list(db.scalars(select(SchemaVersion.version).order_by(SchemaVersion.version)))
 assert versions==[1,2,3,4,5]
start=time.perf_counter();schedule_due();schedule_seconds=time.perf_counter()-start
def claims(index):
 seen=[]
 while True:
  task=claim_task('postgres-verifier-'+str(index))
  if task is None:break
  seen.append(task['id'])
  with SessionLocal() as db:
   db.execute(update(Task).where(Task.id==task['id']).values(status='completed'));db.commit()
 return seen
start=time.perf_counter()
with ThreadPoolExecutor(max_workers=8) as pool:
 batches=list(pool.map(claims,range(8)))
ids=[value for batch in batches for value in batch]
elapsed=time.perf_counter()-start
assert len(ids)==len(set(ids))==1000
with ThreadPoolExecutor(max_workers=8) as pool:
 delays=list(pool.map(lambda _:reserve('synthetic-shared.example.invalid',30),range(8)))
assert sum(delay==0 for delay in delays)==1
print(json.dumps({'database':'PostgreSQL','schema_versions':versions,'encrypted_profile_preserved':True,'sources':1000,'worker_threads':8,'unique_claims':len(set(ids)),'schedule_seconds':round(schedule_seconds,4),'claim_and_complete_seconds':round(elapsed,4),'shared_host_budget_single_reservation':True,'http_requests':0,'external_emails':0,'browser_launches':0,'production_tls_tested':False}))
engine.dispose()
'''


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--container',default='internpilot-validation-postgres-1')
    parser.add_argument('--host',required=True,help='Private bridge IP of the local synthetic PostgreSQL container')
    args=parser.parse_args()
    token=secrets.token_hex(6)
    role='internpilot_verify_'+token
    database='internpilot_upgrade_'+token+'_scratch'
    password=secrets.token_urlsafe(32)
    docker_env={key:value for key,value in os.environ.items() if key not in {'DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH'}}
    command=['docker','--host=unix:///var/run/docker.sock','exec','-i',args.container,'sh','-c','exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1']
    def sql_exec(statement):
        result=subprocess.run(command,input=statement.as_string(),capture_output=True,text=True,env=docker_env,timeout=30)
        if result.returncode:raise RuntimeError('Local scratch PostgreSQL provisioning/cleanup failed; no credential output was printed')
    try:
        sql_exec(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}; CREATE DATABASE {} OWNER {};').format(sql.Identifier(role),sql.Literal(password),sql.Identifier(database),sql.Identifier(role)))
        with tempfile.TemporaryDirectory(prefix='internpilot-pg-verify-') as directory:
            env={**os.environ,'DATABASE_URL':URL.create('postgresql+psycopg',username=role,password=password,host=args.host,port=5432,database=database).render_as_string(hide_password=False),'DATABASE_SSLMODE':'','DATA_DIR':directory,'ENCRYPTION_KEY':Fernet.generate_key().decode(),'ENVIRONMENT':'development','CRAWL_BATCH_SIZE':'2000','REDIS_URL':'','WORKER_KINDS':'discovery','LLM_PROVIDER':'disabled'}
            result=subprocess.run([sys.executable,'-c',PROGRAM],cwd=ROOT/'backend',env=env,capture_output=True,text=True,timeout=180)
            if result.returncode:
                raise RuntimeError('Scratch PostgreSQL verification failed; no credentials or provider exception contents were printed')
            report=json.loads(result.stdout.strip())
            (ROOT/'artifacts/production-postgres.json').write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps(report,indent=2))
    finally:
        sql_exec(sql.SQL('SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname={}; DROP DATABASE IF EXISTS {}; DROP ROLE IF EXISTS {};').format(sql.Literal(database),sql.Identifier(database),sql.Identifier(role)))


if __name__=='__main__':
    main()
