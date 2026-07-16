# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false

import hashlib
import hmac
import json
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import HttpUrl

from incidentecho.api.app import app
from incidentecho.api.dependencies import (
    get_github_client,
    get_incident_repository,
    get_webhook_repository,
)
from incidentecho.config import get_settings
from incidentecho.domain.models import Incident
from incidentecho.domain.repositories import IncidentAlreadyExistsError
from incidentecho.github.checks import CheckRun
from incidentecho.github.client import PullRequestChange


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
    def __init__(self) -> None:
        self.added: dict[str, Incident] = {}

    async def add(self, incident: Incident) -> Incident:
        if incident.incident_id in self.added:
            raise IncidentAlreadyExistsError(incident.incident_id)
        self.added[incident.incident_id] = incident
        return incident

    async def get(self, incident_id: str) -> Incident | None:
        return self.added.get(incident_id)

    async def list(self, **_: int) -> tuple[Incident, ...]:
        return (
            *self.added.values(),
            Incident(
                incident_id="INC-1",
                title="Example service regression",
                summary="A prior change broke the example service.",
                affected_paths=("src/example.py",),
                source_url=HttpUrl("https://github.com/nuthalat/incidentecho/issues/1"),
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
            "repository": {"name": "incidentecho", "owner": {"login": "nuthalat"}},
            "pull_request": {
                "number": 9,
                "title": "Change the example service",
                "body": "Updates production behavior",
                "head": {"sha": "a" * 40},
            },
        }
    ).encode()


def signed_headers(
    body: bytes, delivery_id: str = "delivery-1", event: str = "pull_request"
) -> dict[str, str]:
    signature = hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
    return {
        "X-GitHub-Delivery": delivery_id,
        "X-GitHub-Event": event,
        "X-Hub-Signature-256": f"sha256={signature}",
        "Content-Type": "application/json",
    }


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("INCIDENTECHO_GITHUB_WEBHOOK_SECRET", "test-secret")
    get_settings.cache_clear()
    repository.deliveries.clear()
    incidents.added.clear()
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


def issue_body(*, labels: tuple[str, ...] = ("incident",), pull_request: bool = False) -> bytes:
    issue: dict[str, object] = {
        "id": 123456,
        "number": 17,
        "title": "Queue retry storm",
        "body": "Retries saturated the checkout workers.",
        "html_url": "https://github.com/IncidentEcho/incidentecho/issues/17",
        "labels": [{"name": label} for label in labels],
    }
    if pull_request:
        issue["pull_request"] = {"url": "https://api.github.test/pulls/17"}
    return json.dumps(
        {
            "action": "opened",
            "repository": {"name": "incidentecho", "owner": {"login": "IncidentEcho"}},
            "issue": issue,
        }
    ).encode()


def test_ingests_labeled_issue_with_canonical_evidence(client: TestClient) -> None:
    body = issue_body(labels=("Incident", "queue"))
    headers = signed_headers(body, "issue-delivery-1", event="issues")

    first = client.post("/api/v1/webhooks/github", content=body, headers=headers)
    duplicate = client.post("/api/v1/webhooks/github", content=body, headers=headers)

    assert first.json()["status"] == "accepted"
    assert duplicate.json()["status"] == "duplicate"
    incident = incidents.added["github-issue:123456"]
    assert incident.title == "Queue retry storm"
    assert incident.keywords == frozenset({"incident", "queue"})
    assert str(incident.source_url) == "https://github.com/IncidentEcho/incidentecho/issues/17"


@pytest.mark.parametrize(
    ("body", "delivery_id"),
    [
        (issue_body(labels=("bug",)), "issue-delivery-2"),
        (issue_body(pull_request=True), "issue-delivery-3"),
    ],
)
def test_ignores_unlabeled_issues_and_pull_requests(
    client: TestClient, body: bytes, delivery_id: str
) -> None:
    response = client.post(
        "/api/v1/webhooks/github",
        content=body,
        headers=signed_headers(body, delivery_id, event="issues"),
    )

    assert response.json()["status"] == "ignored"
    assert incidents.added == {}


def test_distinct_delivery_for_existing_issue_is_idempotent(client: TestClient) -> None:
    body = issue_body()

    first = client.post(
        "/api/v1/webhooks/github",
        content=body,
        headers=signed_headers(body, "issue-delivery-4", event="issues"),
    )
    second = client.post(
        "/api/v1/webhooks/github",
        content=body,
        headers=signed_headers(body, "issue-delivery-5", event="issues"),
    )

    assert first.json()["status"] == "accepted"
    assert second.json()["status"] == "accepted"
    assert tuple(incidents.added) == ("github-issue:123456",)
