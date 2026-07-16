"""Secure GitHub webhook ingress."""

import hashlib
import hmac
import json
from typing import Annotated, Literal, cast

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from recallops.api.dependencies import (
    get_github_client,
    get_incident_repository,
    get_webhook_repository,
)
from recallops.config import get_settings
from recallops.domain.models import PullRequestChange as AnalysisChange
from recallops.domain.repositories import IncidentRepository, WebhookDeliveryRepository
from recallops.github.checks import render_check
from recallops.github.client import GitHubClient
from recallops.services.analysis import CatalogCapacityExceededError, PullRequestAnalysisService

router = APIRouter(prefix="/api/v1/webhooks/github", tags=["webhooks"])
Repository = Annotated[WebhookDeliveryRepository, Depends(get_webhook_repository)]
GitHub = Annotated[GitHubClient | None, Depends(get_github_client)]
Incidents = Annotated[IncidentRepository, Depends(get_incident_repository)]
_ACCEPTED_PULL_REQUEST_ACTIONS = frozenset({"opened", "reopened", "synchronize"})


class WebhookReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    delivery_id: str
    event: str
    action: str | None
    status: Literal["accepted", "ignored", "duplicate"]
    changed_files: int | None = Field(default=None, ge=0)
    risk_level: str | None = None


class _Installation(BaseModel):
    id: int = Field(ge=1)


class _Owner(BaseModel):
    login: str = Field(min_length=1)


class _Repository(BaseModel):
    name: str = Field(min_length=1)
    owner: _Owner


class _PullRequest(BaseModel):
    number: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=300)
    body: str | None = None
    head: "_Head"


class _Head(BaseModel):
    sha: str = Field(min_length=7, max_length=64)


class _PullRequestPayload(BaseModel):
    installation: _Installation
    repository: _Repository
    pull_request: _PullRequest


@router.post("", response_model=WebhookReceipt)
async def receive_github_webhook(
    request: Request,
    repository: Repository,
    github: GitHub,
    incidents: Incidents,
    delivery_id: Annotated[str, Header(alias="X-GitHub-Delivery", min_length=1)],
    event: Annotated[str, Header(alias="X-GitHub-Event", min_length=1)],
    signature: Annotated[str, Header(alias="X-Hub-Signature-256", min_length=1)],
) -> WebhookReceipt:
    body = await request.body()
    secret = get_settings().github_webhook_secret
    if secret is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Webhook disabled"
        )
    expected = (
        "sha256=" + hmac.new(secret.get_secret_value().encode(), body, hashlib.sha256).hexdigest()
    )
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    try:
        payload = cast(object, json.loads(body))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON"
        ) from error
    payload_mapping = cast(dict[str, object], payload) if isinstance(payload, dict) else {}
    action_value = payload_mapping.get("action")
    action = action_value if isinstance(action_value, str) else None
    disposition: Literal["accepted", "ignored"] = (
        "accepted"
        if event == "ping" or (event == "pull_request" and action in _ACCEPTED_PULL_REQUEST_ACTIONS)
        else "ignored"
    )
    changed_files: int | None = None
    risk_level: str | None = None
    context: _PullRequestPayload | None = None
    if disposition == "accepted" and event == "pull_request":
        if github is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GitHub App disabled",
            )
        try:
            context = _PullRequestPayload.model_validate(payload_mapping)
        except ValidationError as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid pull-request context",
            ) from error

    created = await repository.record(
        delivery_id=delivery_id,
        event=event,
        action=action,
        payload_sha256=hashlib.sha256(body).hexdigest(),
        disposition=disposition,
    )
    if not created:
        return WebhookReceipt(
            delivery_id=delivery_id,
            event=event,
            action=action,
            status="duplicate",
        )

    if context is not None:
        assert github is not None
        try:
            changes = await github.pull_request_changes(
                installation_id=context.installation.id,
                owner=context.repository.owner.login,
                repository=context.repository.name,
                number=context.pull_request.number,
            )
            report = await PullRequestAnalysisService(
                incidents, catalog_limit=get_settings().analysis_catalog_limit
            ).analyze(
                AnalysisChange(
                    repository=f"{context.repository.owner.login}/{context.repository.name}",
                    number=context.pull_request.number,
                    title=context.pull_request.title,
                    summary=context.pull_request.body or "",
                    changed_files=tuple(change.filename for change in changes),
                )
            )
            await github.publish_check(
                installation_id=context.installation.id,
                owner=context.repository.owner.login,
                repository=context.repository.name,
                check=render_check(report, head_sha=context.pull_request.head.sha),
            )
        except CatalogCapacityExceededError as error:
            await repository.discard(delivery_id)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Incident catalog capacity exceeded",
            ) from error
        except (httpx.HTTPError, ValueError) as error:
            await repository.discard(delivery_id)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Unable to retrieve pull-request context",
            ) from error
        changed_files = len(changes)
        risk_level = report.risk_level.value
    return WebhookReceipt(
        delivery_id=delivery_id,
        event=event,
        action=action,
        status=disposition,
        changed_files=changed_files,
        risk_level=risk_level,
    )
