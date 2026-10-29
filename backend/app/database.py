from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import settings


class Base(DeclarativeBase):
    pass


connection_args = {"check_same_thread": False, "timeout": 30} if settings.database_url.startswith("sqlite") else {"connect_timeout": 10}
if not settings.database_url.startswith("sqlite") and settings.database_sslmode:
    connection_args["sslmode"] = settings.database_sslmode
pool_options = {} if settings.database_url.startswith("sqlite") else {
    "pool_size":settings.db_pool_size, "max_overflow":settings.db_max_overflow,
    "pool_timeout":settings.db_pool_timeout, "pool_recycle":settings.db_pool_recycle,
}
engine = create_engine(settings.database_url, pool_pre_ping=True, hide_parameters=True, connect_args=connection_args, **pool_options)
if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def sqlite_config(dbapi_connection, _):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")
        dbapi_connection.execute("PRAGMA journal_mode=WAL")

SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_db():
    with SessionLocal() as session:
        yield session
