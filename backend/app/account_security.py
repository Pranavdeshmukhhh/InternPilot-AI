"""Account mutations share a lock with sign-in and session issuance."""
from sqlalchemy import delete, select, update

from .models import LoginSession, User


def locked_user(db, *, user_id=None, email_hash=None):
    condition = User.id == user_id if user_id is not None else User.email_hash == email_hash
    if db.get_bind().dialect.name == "sqlite":
        # SQLite ignores FOR UPDATE. Acquire its write lock before reading a
        # password so a concurrent recovery cannot leave a stale login valid.
        db.execute(update(User).where(condition).values(id=User.id).execution_options(synchronize_session=False))
    return db.scalar(select(User).where(condition).with_for_update().execution_options(populate_existing=True))


def revoke_sessions(db, user_id, *, except_token_hash=None):
    query = delete(LoginSession).where(LoginSession.user_id == user_id)
    if except_token_hash is not None:
        query = query.where(LoginSession.token_hash != except_token_hash)
    result = db.execute(query.execution_options(synchronize_session=False))
    return result.rowcount
