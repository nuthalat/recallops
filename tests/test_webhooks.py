# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false

import hashlib
import hmac
import json
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import HttpUrl

from recallops.api.app import app
from recallops.api.dependencies import (
    get_github_client,
    get_incident_repository,
    get_webhook_repository,
)
from recallops.config import get_settings
from recallops.domain.models import Incident
from recallops.github.checks import CheckRun
from recallops.github.client import PullRequestChange


class MemoryWebhookRepository:
    def __init__(self) -> None:
        self.deliveries: dict[str, str] = {}

    async def record(self, **values: str | None) -> bool:
        delivery_id = values["delivery_id"]
        assert isinstance(delivery_id, str)
        if delivery_id in self.deliveries:
            return False
        disposition = values["disposition"]
        assert isinstance(disposition, str)
        self.deliveries[delivery_id] = disposition
        return True

    async def discard(self, delivery_id: str) -> None:
        self.deliveries.pop(delivery_id, None)


repository = MemoryWebhookRepository()


class MemoryGitHubClient:
    def __init__(self) -> None:
        self.fail = False
        self.fail_publication = False
        self.published: list[CheckRun] = []

    async def pull_request_changes(self, **_: int | str) -> tuple[PullRequestChange, ...]:
        if self.fail:
            request = httpx.Request("GET", "https://api.github.test/pulls/1/files")
            raise httpx.HTTPStatusError(
                "forbidden", request=request, response=httpx.Response(403, request=request)
            )
        return (
            PullRequestChange(
                filename="src/example.py",
                status="modified",
                additions=2,
                deletions=1,
                changes=3,
            ),
        )

    async def publish_check(self, **values: int | str | CheckRun) -> None:
        if self.fail_publication:
            request = httpx.Request("POST", "https://api.github.test/check-runs")
            raise httpx.HTTPStatusError(
                "forbidden", request=request, response=httpx.Response(403, request=request)
            )
        check = values["check"]
        assert isinstance(check, CheckRun)
        self.published.append(check)


github = MemoryGitHubClient()


class MemoryIncidentRepository:
    async def list(self, **_: int) -> tuple[Incident, ...]:
        return (
            Incident(
                incident_id="INC-1",
                title="Example service regression",
                summary="A prior change broke the example service.",
                affected_paths=("src/example.py",),
                source_url=HttpUrl("https://github.com/nuthalat/recallops/issues/1"),
            ),
        )


incidents = MemoryIncidentRepository()


async def override_repository() -> AsyncIterator[MemoryWebhookRepository]:
    yield repository


async def override_github() -> AsyncIterator[MemoryGitHubClient]:
    yield github


async def override_incidents() -> AsyncIterator[MemoryIncidentRepository]:
    yield incidents


def pull_request_body(action: str) -> bytes:
    return json.dumps(
        {
            "action": action,
            "installation": {"id": 77},
            "repository": {"name": "recallops", "owner": {"login": "nuthalat"}},
            "pull_request": {
                "number": 9,
                "title": "Change the example service",
                "body": "Updates production behavior",
                "head": {"sha": "a" * 40},
            },
        }
    ).encode()


def signed_headers(body: bytes, delivery_id: str = "delivery-1") -> dict[str, str]:
    signature = hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
    return {
        "X-GitHub-Delivery": delivery_id,
        "X-GitHub-Event": "pull_request",
        "X-Hub-Signature-256": f"sha256={signature}",
        "Content-Type": "application/json",
    }


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("RECALLOPS_GITHUB_WEBHOOK_SECRET", "test-secret")
    get_settings.cache_clear()
    repository.deliveries.clear()
    github.fail = False
    github.fail_publication = False
    github.published.clear()
    app.dependency_overrides[get_webhook_repository] = override_repository
    app.dependency_overrides[get_github_client] = override_github
    app.dependency_overrides[get_incident_repository] = override_incidents
    yield TestClient(app)
    app.dependency_overrides.pop(get_webhook_repository, None)
    app.dependency_overrides.pop(get_github_client, None)
    app.dependency_overrides.pop(get_incident_repository, None)
    get_settings.cache_clear()


def test_accepts_and_deduplicates_signed_pull_request(client: TestClient) -> None:
    body = pull_request_body("synchronize")

    first = client.post("/api/v1/webhooks/github", content=body, headers=signed_headers(body))
    duplicate = client.post("/api/v1/webhooks/github", content=body, headers=signed_headers(body))

    assert first.status_code == 200
    assert first.json()["status"] == "accepted"
    assert first.json()["changed_files"] == 1
    assert first.json()["risk_level"] == "medium"
    assert github.published[0].head_sha == "a" * 40
    assert github.published[0].conclusion == "neutral"
    assert duplicate.json()["status"] == "duplicate"
    assert len(github.published) == 1


def test_rejects_invalid_signature_before_persistence(client: TestClient) -> None:
    body = pull_request_body("opened")
    headers = signed_headers(body)
    headers["X-Hub-Signature-256"] = "sha256=invalid"

    response = client.post("/api/v1/webhooks/github", content=body, headers=headers)

    assert response.status_code == 401
    assert repository.deliveries == {}


def test_records_unsupported_action_as_ignored(client: TestClient) -> None:
    body = b'{"action":"closed"}'

    response = client.post(
        "/api/v1/webhooks/github", content=body, headers=signed_headers(body, "delivery-2")
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


def test_rejects_malformed_pull_request_context(client: TestClient) -> None:
    body = b'{"action":"opened"}'

    response = client.post(
        "/api/v1/webhooks/github", content=body, headers=signed_headers(body, "delivery-3")
    )

    assert response.status_code == 400
    assert "delivery-3" not in repository.deliveries


def test_github_api_failure_does_not_report_success(client: TestClient) -> None:
    github.fail = True
    body = pull_request_body("opened")

    response = client.post(
        "/api/v1/webhooks/github", content=body, headers=signed_headers(body, "delivery-4")
    )

    assert response.status_code == 502
    assert "delivery-4" not in repository.deliveries


def test_check_publication_failure_releases_delivery_for_retry(client: TestClient) -> None:
    github.fail_publication = True
    body = pull_request_body("opened")

    response = client.post(
        "/api/v1/webhooks/github", content=body, headers=signed_headers(body, "delivery-5")
    )

    assert response.status_code == 502
    assert "delivery-5" not in repository.deliveries
    assert github.published == []
