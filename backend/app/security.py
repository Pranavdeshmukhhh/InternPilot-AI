import hashlib
import hmac
import json
import os
import secrets
from cryptography.fernet import Fernet
from .config import settings


def _load_key():
    if settings.encryption_key:
        return settings.encryption_key.encode()
    path = settings.data_dir / "encryption.key"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return path.read_bytes().strip()
    key = Fernet.generate_key()
    with os.fdopen(fd, "wb") as stream:
        stream.write(key)
    return key


fernet = Fernet(_load_key())


def encrypt(value):
    return fernet.encrypt(json.dumps(value, ensure_ascii=False).encode())


def decrypt(value):
    return json.loads(fernet.decrypt(value))


def encrypt_bytes(value: bytes):
    return fernet.encrypt(value)


def decrypt_bytes(value: bytes):
    return fernet.decrypt(value)


def digest(value: str):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password: str):
    salt = secrets.token_bytes(16)
    result = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return f"scrypt${salt.hex()}${result.hex()}"


def verify_password(password: str, encoded: str):
    try:
        _, salt, expected = encoded.split("$")
        result = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
        return hmac.compare_digest(result.hex(), expected)
    except (ValueError, TypeError):
        return False


def approval_digest(profile: dict, job: dict, document_id: str | None):
    return digest(json.dumps({"profile":profile,"job":job,"document_id":document_id}, sort_keys=True, default=str))
