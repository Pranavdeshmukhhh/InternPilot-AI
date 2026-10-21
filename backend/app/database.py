from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import settings


class Base(DeclarativeBase):
    pass


connection_args = {"check_same_thread": False, "timeout": 30} if settings.database_url.startswith("sqlite") else {"connect_timeout": 10}
if not settings.database_url.startswith("sqlite") and settings.database_sslmode:
    connection_args["sslmode"] = settings.database_sslmode
engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connection_args)
if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def sqlite_config(dbapi_connection, _):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")
        dbapi_connection.execute("PRAGMA journal_mode=WAL")

SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_db():
    with SessionLocal() as session:
        yield session
