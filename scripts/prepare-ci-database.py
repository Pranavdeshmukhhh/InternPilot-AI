"""Provision a disposable, non-superuser PostgreSQL role/database in GitHub CI.

Only localhost and CI=true with GITHUB_ENV are accepted. This is not deployment
or production database setup. Ephemeral credentials are written to GITHUB_ENV,
never printed or committed; the service container disappears after the job.
"""
import os
import secrets
from pathlib import Path
from uuid import uuid4


def main():
    from psycopg import sql
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url
    if os.getenv("CI") != "true" or not os.getenv("GITHUB_ENV"):
        raise SystemExit("This helper is for disposable GitHub CI service containers only")
    url = make_url(os.environ["CI_POSTGRES_ADMIN_URL"])
    if url.host not in {"localhost", "127.0.0.1"} or url.database != "postgres":
        raise SystemExit("CI admin URL must target the local postgres service database")
    role, database = "lab_" + uuid4().hex[:12], "phase7_" + uuid4().hex[:12]
    password = secrets.token_urlsafe(32)
    engine = create_engine(url, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        driver = conn.connection.driver_connection
        driver.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE").format(sql.Identifier(role), sql.Literal(password)))
        driver.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(database), sql.Identifier(role)))
        driver.execute(sql.SQL("COMMENT ON DATABASE {} IS {}").format(sql.Identifier(database), sql.Literal("InternPilot Phase7 synthetic benchmark only")))
    engine.dispose()
    lab = url.set(username=role, password=password, database=database)
    with Path(os.environ["GITHUB_ENV"]).open("a") as stream:
        stream.write("PHASE4_POSTGRES_URL=" + lab.render_as_string(hide_password=False) + "\n")
    print("Disposable non-superuser PostgreSQL test database prepared.")


if __name__ == "__main__":
    main()
