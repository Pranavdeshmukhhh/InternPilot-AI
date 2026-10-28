"""Measure 1,000-source scheduling/claiming in an isolated real SQLite database.

No HTTP/browser work is executed. This is a database-queue benchmark, never a
claim of 1,000 live websites crawled. The user's database is not opened.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[1]
PROGRAM = '''
import json,time
from sqlalchemy import select,update
from app.migrate import migrate
from app.database import SessionLocal
from app.models import User,Source,Task
from app.schemas import Profile,Policy
from app.security import encrypt,digest
from app.worker import schedule_due,claim_task
migrate()
with SessionLocal() as db:
 user=User(email_hash=digest('benchmark@example.invalid'),email_encrypted=encrypt('benchmark@example.invalid'),password_hash='unused-benchmark',profile_encrypted=encrypt(Profile().model_dump()),policy_encrypted=encrypt(Policy().model_dump()))
 db.add(user);db.flush()
 db.add_all([Source(owner_id=user.id,kind='greenhouse',slug=f'synthetic-{i}',company='SYNTHETIC queue benchmark',enabled=True,permitted=True) for i in range(1000)])
 db.commit()
start=time.perf_counter();schedule_due();scheduled=time.perf_counter()-start
start=time.perf_counter();seen=set()
while True:
 task=claim_task('isolated-benchmark')
 if not task:break
 assert task['id'] not in seen
 seen.add(task['id'])
 with SessionLocal() as db:
  db.execute(update(Task).where(Task.id==task['id']).values(status='completed'));db.commit()
elapsed=time.perf_counter()-start
assert len(seen)==1000
print(json.dumps({'database':'isolated_sqlite','sources':1000,'unique_claims':len(seen),'schedule_seconds':round(scheduled,4),'claim_and_complete_seconds':round(elapsed,4),'claims_per_second':round(1000/elapsed,2),'http_requests':0,'browser_launches':0,'note':'Real database queue measurement. Not a network or production PostgreSQL throughput claim.'}))
'''


def main():
    with tempfile.TemporaryDirectory(prefix="internpilot-benchmark-") as directory:
        env = {**os.environ,"DATA_DIR":directory,"DATABASE_URL":f"sqlite:///{Path(directory)/'benchmark.db'}","ENCRYPTION_KEY":Fernet.generate_key().decode(),"CRAWL_BATCH_SIZE":"2000","ENVIRONMENT":"development","REDIS_URL":"","LLM_PROVIDER":"disabled"}
        result = subprocess.run([sys.executable,"-c",PROGRAM],cwd=ROOT/"backend",env=env,text=True,capture_output=True,timeout=120,check=True)
        report = json.loads(result.stdout.strip())
        (ROOT/"artifacts/cloud-queue-benchmark.json").write_text(json.dumps(report,indent=2)+"\n")
        print(json.dumps(report,indent=2))


if __name__=="__main__":
    main()
