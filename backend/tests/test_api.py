"""REST API tests using a throw-away in-memory SQLite database."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_session
from app.main import app

PLAN = {
    "destination_id": "mysuru", "start_date": "2026-10-19", "days": 2, "travelers": 2,
    "budget": 25000, "accommodation": "standard", "pace": "moderate",
    "interests": ["history", "nature"], "must_visit": ["mysore_zoo"], "exclude": ["devaraja_market"],
}


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)

    def override():
        with TestSession() as session:
            yield session

    app.dependency_overrides[get_session] = override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_health_and_destinations(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    destinations = client.get("/api/destinations").json()
    assert {d["id"] for d in destinations} == {
        "agra", "goa", "jaipur", "mysuru", "puducherry", "varanasi"
    }


def test_destination_detail_shows_inherited_properties(client):
    data = client.get("/api/destinations/jaipur").json()
    birla = next(a for a in data["attractions"] if a["id"] == "birla_mandir")
    assert birla["lineage"][0] == "Temple"
    assert birla["properties"]["footwear_removed"] == {"value": True, "source": "Temple"}
    assert client.get("/api/destinations/unknown-city").status_code == 404


def test_plan_endpoint(client):
    response = client.post("/api/plan", json=PLAN)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert all(check["passed"] for check in body["checks"])
    assert body["decomposition"]["task"] == "plan_trip(2)"


def test_plan_validation_errors(client):
    assert client.post("/api/plan", json={**PLAN, "days": 0}).status_code == 422
    assert client.post("/api/plan", json={**PLAN, "interests": ["golf"]}).status_code == 422
    clash = client.post("/api/plan", json={**PLAN, "exclude": ["mysore_zoo"]})
    assert clash.status_code == 422 and "both" in clash.json()["detail"]
    assert client.post("/api/plan", json={**PLAN, "must_visit": ["taj_mahal"]}).status_code == 422


def test_infeasible_plan_is_a_normal_response(client):
    body = client.post("/api/plan", json={**PLAN, "budget": 1000}).json()
    assert body["status"] == "infeasible"
    assert body["issues"]


def test_logic_query_endpoint(client):
    body = client.post("/api/knowledge/query",
                       json={"destination_id": "puducherry", "query": "member_of(?X, Beach)"}).json()
    assert {a["bindings"]["?X"] for a in body["answers"]} == {"promenade_beach", "paradise_beach"}
    bad = client.post("/api/knowledge/query", json={"destination_id": "puducherry", "query": "member_of(?X"})
    assert bad.status_code == 422
    assert client.get("/api/knowledge/puducherry").json()["rules"]


def test_save_list_get_delete(client):
    saved = client.post("/api/itineraries", json={"title": "Mysuru weekend", "request": PLAN})
    assert saved.status_code == 201
    itinerary_id = saved.json()["id"]
    listing = client.get("/api/itineraries").json()
    assert [row["title"] for row in listing] == ["Mysuru weekend"]
    detail = client.get(f"/api/itineraries/{itinerary_id}").json()
    assert detail["result"]["status"] == "ok"
    assert client.delete(f"/api/itineraries/{itinerary_id}").status_code == 204
    assert client.get(f"/api/itineraries/{itinerary_id}").status_code == 404


def test_cannot_save_infeasible_plan(client):
    response = client.post("/api/itineraries", json={"title": "Too cheap", "request": {**PLAN, "budget": 1000}})
    assert response.status_code == 422
