# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false

from fastapi.testclient import TestClient

from recallops.api.app import app

client = TestClient(app)


def test_liveness_contract() -> None:
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "recallops", "version": "0.1.0"}


def test_readiness_contract() -> None:
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
