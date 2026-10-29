"""Legacy catalog upgrade reproducer using actual local HTTP requests."""
# ruff: noqa: F811 -- imported pytest fixture is injected by name.
import pytest
from test_api_worker import stack  # noqa: F401


def legacy(stack, user):
    stack.python("""
from app.database import engine
from app.models import Opportunity,Source,SourceOpportunity,now
from sqlalchemy import select
with engine.begin() as conn:
 source=conn.scalar(select(Source.id).where(Source.owner_id==%r).limit(1))
 conn.execute(Opportunity.__table__.insert().values(id='startup-legacy',fingerprint='startup-legacy',data={'title':'Synthetic Intern','company':'Local fixture','url':'https://example.invalid/local','active':True},projection_version=0,first_discovered=now(),last_verified=now()))
 conn.execute(SourceOpportunity.__table__.insert().values(source_id=source,opportunity_id='startup-legacy'))
""" % user)


def startup(stack):
    stack.python("""
import asyncio
from app.main import app,lifespan
async def boot():
 async with lifespan(app):pass
asyncio.run(boot())
""")


def test_local_startup_repairs_pending_overview_without_changing_ids(stack):
    client,account=stack.register()
    legacy(stack,account['user']['id'])
    assert client.get('/api/v2/opportunities').status_code==409
    assert client.get('/api/ready').status_code==503
    startup(stack)
    assert client.get('/api/v2/opportunities').status_code==200
    assert client.get('/api/ready').status_code==200
    assert client.get('/api/dashboard').status_code==200
    startup(stack)
    with stack.db() as db:
        row=db.execute("SELECT id,projection_version FROM opportunities WHERE id='startup-legacy'").fetchone()
        assert tuple(row)==('startup-legacy',1)
        assert db.execute("SELECT count(*) FROM source_opportunities WHERE opportunity_id='startup-legacy'").fetchone()[0]==1


@pytest.mark.parametrize('stack',[{'AUTO_CATALOG_BACKFILL':'false'}],indirect=True)
def test_explicit_backfill_optout_stays_unready_until_operator_repairs(stack):
    client,account=stack.register()
    legacy(stack,account['user']['id'])
    startup(stack)
    assert client.get('/api/ready').status_code==503
    assert client.get('/api/v2/opportunities').status_code==409
    stack.python('from app.catalog_migrations import backfill; from app.database import engine; backfill(engine)')
    assert client.get('/api/v2/opportunities').status_code==200
