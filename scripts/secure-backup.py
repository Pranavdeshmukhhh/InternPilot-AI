"""Stream-encrypted PostgreSQL backups. No database password enters argv or logs.

Run with the backend environment and pg_dump installed. Restore is deliberately
separate: --decrypt writes a new dump file; it never overwrites a database.
"""
import argparse
import base64
import os
import subprocess
import sys
import threading
from pathlib import Path
from urllib.parse import unquote, urlsplit

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

MAGIC = b"IPBK1"
CHUNK = 1024*1024


def derive(key,salt):
    return HKDF(algorithm=hashes.SHA256(),length=32,salt=salt,info=b"InternPilot database backup v1").derive(base64.urlsafe_b64decode(key))


def encrypt_stream(source,target,key):
    salt,nonce = os.urandom(16),os.urandom(12)
    cipher = Cipher(algorithms.AES(derive(key,salt)),modes.GCM(nonce)).encryptor()
    header = MAGIC+salt+nonce
    cipher.authenticate_additional_data(header)
    target.write(header)
    while chunk:=source.read(CHUNK):
        target.write(cipher.update(chunk))
    target.write(cipher.finalize());target.write(cipher.tag)


def decrypt_stream(source,target,key):
    header=source.read(len(MAGIC)+28)
    if len(header)!=33 or not header.startswith(MAGIC):
        raise ValueError("Unsupported backup")
    source.seek(-16,os.SEEK_END);tag=source.read(16);end=source.tell()-16
    source.seek(len(header))
    cipher=Cipher(algorithms.AES(derive(key,header[5:21])),modes.GCM(header[21:33],tag)).decryptor()
    cipher.authenticate_additional_data(header)
    while source.tell()<end:
        target.write(cipher.update(source.read(min(CHUNK,end-source.tell()))))
    target.write(cipher.finalize())


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("output",type=Path)
    parser.add_argument("--decrypt",type=Path)
    parser.add_argument("--timeout",type=int,default=120,help="Hard pg_dump wall-time budget in seconds")
    args=parser.parse_args()
    if not 1 <= args.timeout <= 86400:
        parser.error("Backup timeout must be between 1 and 86400 seconds")
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
    from app.config import settings
    from app.security import _load_key
    key=_load_key()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    # Exclusive creation prevents an accidental overwrite of an existing backup.
    fd=os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(fd,"wb") as target:
            if args.decrypt:
                with args.decrypt.open("rb") as source:decrypt_stream(source,target,key)
            else:
                url=urlsplit(settings.database_url.replace("postgresql+psycopg://","postgresql://",1))
                if url.scheme!="postgresql":raise ValueError("Use PostgreSQL for cloud database backups")
                env={**os.environ,"PGHOST":url.hostname or "","PGPORT":str(url.port or 5432),"PGUSER":unquote(url.username or ""),"PGPASSWORD":unquote(url.password or ""),"PGDATABASE":url.path.lstrip("/"),"PGCONNECT_TIMEOUT":"10"}
                if settings.database_sslmode:env["PGSSLMODE"]=settings.database_sslmode
                with subprocess.Popen(["pg_dump","--format=custom","--no-owner","--no-acl"],env=env,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL) as process:
                    # wait(timeout) alone does not bound a blocking stdout read.
                    watchdog=threading.Timer(args.timeout,process.kill)
                    watchdog.daemon=True;watchdog.start()
                    try:encrypt_stream(process.stdout,target,key)
                    except BaseException:
                        # A disk error/cancellation must not leave __exit__
                        # waiting forever for an otherwise stalled pg_dump.
                        process.kill()
                        raise
                    finally:
                        watchdog.cancel()
                        process.stdout.close()
                    if process.wait(timeout=120)!=0:raise RuntimeError("pg_dump failed; inspect database connectivity without exposing credentials")
        print("Authenticated encrypted backup completed." if not args.decrypt else "Backup authenticated and decrypted. No database was modified.")
    except BaseException:
        args.output.unlink(missing_ok=True)
        raise


if __name__=="__main__":
    main()
