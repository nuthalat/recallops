# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false

from collections.abc import AsyncIterator

from fastapi.testclient import TestClient
from pydantic import HttpUrl

from incidentecho.api.app import app
from incidentecho.api.dependencies import get_incident_repository
from incidentecho.domain.models import Incident
from incidentecho.domain.repositories import IncidentAlreadyExistsError, IncidentRepository


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
    assert response.json() == {"status": "ok", "service": "incidentecho", "version": "0.1.0"}


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


def test_analysis_returns_explainable_persisted_evidence() -> None:
    repository.incidents.clear()
    repository.incidents["INC-88"] = Incident(
        incident_id="INC-88",
        title="Payment retry storm",
        summary="Retries exhausted payment capacity.",
        affected_paths=("src/payments/*.py",),
        keywords=frozenset({"payment", "retry"}),
        source_url=HttpUrl("https://example.com/incidents/88"),
    )

    response = client.post(
        "/api/v1/analysis",
        json={
            "repository": "acme/payments",
            "number": 42,
            "title": "Adjust payment retry",
            "changed_files": ["src/payments/retry.py"],
        },
    )

    assert response.status_code == 200
    assert response.json()["risk_level"] == "high"
    assert response.json()["evidence"][0]["incident_id"] == "INC-88"


def test_analysis_is_quiet_without_evidence() -> None:
    repository.incidents.clear()

    response = client.post(
        "/api/v1/analysis",
        json={
            "repository": "acme/catalog",
            "number": 7,
            "title": "Update catalog",
            "changed_files": ["src/catalog.py"],
        },
    )

    assert response.status_code == 200
    assert response.json()["risk_level"] == "none"
    assert response.json()["evidence"] == []


def test_analysis_rejects_catalog_larger_than_configured_capacity() -> None:
    repository.incidents = {
        f"INC-{index}": Incident(incident_id=f"INC-{index}", title="Incident", summary="Summary")
        for index in range(1001)
    }

    response = client.post(
        "/api/v1/analysis",
        json={
            "repository": "acme/catalog",
            "number": 8,
            "title": "Update catalog",
            "changed_files": ["src/catalog.py"],
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Incident catalog exceeds deterministic analysis capacity"
