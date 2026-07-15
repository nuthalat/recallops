"""Secure GitHub webhook ingress."""

import hashlib
import hmac
import json
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict

from recallops.api.dependencies import get_webhook_repository
from recallops.config import get_settings
from recallops.domain.repositories import WebhookDeliveryRepository

router = APIRouter(prefix="/api/v1/webhooks/github", tags=["webhooks"])
Repository = Annotated[WebhookDeliveryRepository, Depends(get_webhook_repository)]
_ACCEPTED_PULL_REQUEST_ACTIONS = frozenset({"opened", "reopened", "synchronize"})


class WebhookReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    delivery_id: str
    event: str
    action: str | None
    status: Literal["accepted", "ignored", "duplicate"]


@router.post("", response_model=WebhookReceipt)
async def receive_github_webhook(
    request: Request,
    repository: Repository,
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
    created = await repository.record(
        delivery_id=delivery_id,
        event=event,
        action=action,
        payload_sha256=hashlib.sha256(body).hexdigest(),
        disposition=disposition,
    )
    receipt_status: Literal["accepted", "ignored", "duplicate"] = (
        disposition if created else "duplicate"
    )
    return WebhookReceipt(
        delivery_id=delivery_id, event=event, action=action, status=receipt_status
    )
