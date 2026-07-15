"""FastAPI dependency adapters."""

from collections.abc import AsyncIterator
from typing import cast

from fastapi import Request

from recallops.config import get_settings
from recallops.domain.repositories import IncidentRepository, WebhookDeliveryRepository
from recallops.github.client import GitHubAppClient, GitHubClient
from recallops.persistence.database import SessionFactory, session_scope
from recallops.persistence.incidents import SqlAlchemyIncidentRepository
from recallops.persistence.webhooks import SqlAlchemyWebhookDeliveryRepository


async def get_incident_repository(request: Request) -> AsyncIterator[IncidentRepository]:
    """Provide one transactional incident repository per request."""

    factory = cast(SessionFactory, request.app.state.session_factory)
    async with session_scope(factory) as session:
        yield SqlAlchemyIncidentRepository(session)


async def get_webhook_repository(
    request: Request,
) -> AsyncIterator[WebhookDeliveryRepository]:
    """Provide one transactional webhook-delivery repository per request."""

    factory = cast(SessionFactory, request.app.state.session_factory)
    async with session_scope(factory) as session:
        yield SqlAlchemyWebhookDeliveryRepository(session)


async def get_github_client() -> AsyncIterator[GitHubClient | None]:
    """Provide a configured, request-scoped GitHub App client."""

    settings = get_settings()
    if settings.github_app_id is None or settings.github_app_private_key is None:
        yield None
        return
    async with GitHubAppClient(
        app_id=settings.github_app_id, private_key=settings.github_app_private_key
    ) as client:
        yield client
