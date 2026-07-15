# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false

from collections.abc import AsyncIterator

from fastapi.testclient import TestClient

from recallops.api.app import app
from recallops.api.dependencies import get_incident_repository
from recallops.domain.models import Incident
from recallops.domain.repositories import IncidentAlreadyExistsError, IncidentRepository


class MemoryIncidentRepository:
    def __init__(self) -> None:
        self.incidents: dict[str, Incident] = {}

    async def add(self, incident: Incident) -> Incident:
        if incident.incident_id in self.incidents:
            raise IncidentAlreadyExistsError(incident.incident_id)
        self.incidents[incident.incident_id] = incident
        return incident

    async def get(self, incident_id: str) -> Incident | None:
        return self.incidents.get(incident_id)

    async def list(self, *, limit: int, offset: int) -> tuple[Incident, ...]:
        return tuple(self.incidents.values())[offset : offset + limit]


repository = MemoryIncidentRepository()


async def override_repository() -> AsyncIterator[IncidentRepository]:
    yield repository


app.dependency_overrides[get_incident_repository] = override_repository
client = TestClient(app)


def test_liveness_contract() -> None:
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "recallops", "version": "0.1.0"}


def test_readiness_contract() -> None:
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_incident_catalog_contract() -> None:
    repository.incidents.clear()
    payload = {
        "incident_id": "INC-42",
        "title": "Checkout latency",
        "summary": "Connection pool exhaustion increased checkout latency.",
        "affected_paths": ["src/Checkout.py"],
        "keywords": ["Pool", "Latency"],
        "source_url": "https://example.com/incidents/42",
    }

    created = client.post("/api/v1/incidents", json=payload)
    fetched = client.get("/api/v1/incidents/INC-42")
    listed = client.get("/api/v1/incidents")

    assert created.status_code == 201
    assert created.json()["affected_paths"] == ["src/checkout.py"]
    assert fetched.status_code == 200
    assert listed.json() == [created.json()]


def test_duplicate_and_missing_incidents_have_stable_errors() -> None:
    repository.incidents.clear()
    payload = {"incident_id": "INC-7", "title": "Rollback", "summary": "Bad deploy."}

    assert client.post("/api/v1/incidents", json=payload).status_code == 201
    duplicate = client.post("/api/v1/incidents", json=payload)
    missing = client.get("/api/v1/incidents/unknown")

    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "Incident 'INC-7' already exists"
    assert missing.status_code == 404
