"""Real API/persistence with mocked destination validation; no network crawling."""
import hashlib
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import operations_api
from app.database import Base, get_db
from app.models import Source


def candidate(slug="tiny-lab", **changes):
    row = {"kind": "ashby", "slug": slug, "url": None, "company": "SYNTHETIC small employer",
           "evidence_url": "https://example.com/careers", "discovered_at": "2026-10-26T10:00:00+00:00",
           "reason": "Public board link discovered on a publisher page.", "verified": False}
    row.update(changes)
    row["id"] = hashlib.sha256(":".join(operations_api.candidate_key(row)).encode()).hexdigest()[:24]
    return row


@pytest.fixture
def review(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    owner = SimpleNamespace(id="candidate-owner")
    checks, locks = [], []
    async def validate(url):
        checks.append(url)
        return url
    def lock(request, user, db):
        locks.append(user.id)
        return user
    def database():
        with sessions() as db:
            yield db
    monkeypatch.setattr(operations_api, "validate_public_url", validate)
    app = FastAPI()
    app.include_router(operations_api.create_router(lambda: owner, lock))
    app.dependency_overrides[get_db] = database
    def seed(items, owner_id="candidate-owner", **cache):
        with sessions() as db:
            row = Source(owner_id=owner_id, kind="search", slug="synthetic query", company="SYNTHETIC search", permitted=True, enabled=True,
                         cache={"source_candidates": items, **cache})
            db.add(row); db.commit()
            return row.id
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, seed=seed, sessions=sessions, owner=owner, checks=checks, locks=locks)
    engine.dispose()


def test_review_is_owner_scoped_and_deduplicates_discoveries(review):
    row = candidate()
    review.seed([row, row])
    review.seed([row])
    review.seed([candidate("private-employer")], owner_id="another-owner")
    response = review.client.get("/api/discovery/source-candidates")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1 and data["items"][0]["verified"] is False
    assert "unverified" in data["note"]
    assert review.checks == []
    assert review.client.post("/api/discovery/source-candidates/unknown/install", json={"permitted": True}).status_code == 404


def test_enable_requires_permission_validates_destination_and_is_idempotent(review):
    row = candidate()
    review.seed([row])
    path = "/api/discovery/source-candidates/" + row["id"] + "/install"
    assert review.client.post(path, json={}).status_code == 422
    assert review.client.post(path, json={"permitted": False}).status_code == 422
    assert review.client.post(path, json={"permitted": True, "company": "tampered"}).status_code == 422
    response = review.client.post(path, json={"permitted": True})
    assert response.status_code == 200, response.text
    installed = response.json()
    assert installed["kind"] == "ashby" and installed["slug"] == row["slug"]
    assert installed["enabled"] and installed["permitted"]
    assert installed["last_success"] is None
    assert review.checks == [row["evidence_url"]]
    assert review.locks == ["candidate-owner"]
    assert review.client.get("/api/discovery/source-candidates").json()["total"] == 0
    assert review.client.post(path, json={"permitted": True}).json()["id"] == installed["id"]
    with review.sessions() as db:
        assert len(list(db.scalars(select(Source)))) == 2


def test_page_source_validation_and_manual_fallback_do_not_assert_verified_jobs(review):
    row = candidate("", kind="html", url="https://example.com/careers?utm_source=a")
    review.seed([row])
    response = review.client.post("/api/discovery/source-candidates/" + row["id"] + "/install", json={"permitted": True})
    assert response.status_code == 200
    assert review.checks == [row["evidence_url"], row["url"]]
    assert response.json()["discovered_count"] == 0


def test_dns_revalidation_failure_prevents_install(review, monkeypatch):
    row = candidate()
    review.seed([row])
    async def blocked(url):
        raise ValueError("private destination")
    monkeypatch.setattr(operations_api, "validate_public_url", blocked)
    response = review.client.post("/api/discovery/source-candidates/" + row["id"] + "/install", json={"permitted": True})
    assert response.status_code == 422
    assert review.client.get("/api/discovery/source-candidates").json()["total"] == 1


def test_dismiss_persists_across_search_parents_and_does_not_touch_other_owner(review):
    row = candidate()
    review.seed([row]); review.seed([row])
    private_id = review.seed([row], owner_id="another-owner")
    response = review.client.post("/api/discovery/source-candidates/" + row["id"] + "/dismiss")
    assert response.status_code == 200
    assert review.client.get("/api/discovery/source-candidates").json()["total"] == 0
    with review.sessions() as db:
        assert db.get(Source, private_id).cache.get("dismissed_source_candidate_ids") is None
        assert all(row["id"] in item.cache["dismissed_source_candidate_ids"] for item in db.scalars(select(Source).where(Source.owner_id == review.owner.id)))


def test_review_rejects_malformed_unsafe_and_unexpected_candidate_types(review):
    valid = candidate()
    tampered = {**candidate("tampered"), "id": "wrong"}
    review.seed([valid, tampered, {"id": "incomplete"}, "not an object", candidate("", kind="search"),
                 candidate("private", evidence_url="https://127.0.0.1/internal"),
                 candidate("blocked", evidence_url="https://linkedin.com/jobs"),
                 candidate("", kind="html", url="javascript:alert(1)")])
    result = review.client.get("/api/discovery/source-candidates").json()
    assert result["total"] == 1 and result["items"][0]["id"] == valid["id"]


def test_review_list_is_bounded_without_discarding_total(review):
    for batch in range(6):
        review.seed([candidate(f"small-{batch}-{index}") for index in range(20)])
    result = review.client.get("/api/discovery/source-candidates").json()
    assert result["total"] == 120 and len(result["items"]) == 100
