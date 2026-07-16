"""FastAPI dependency adapters."""

from collections.abc import AsyncIterator
from typing import cast

from fastapi import Request

from incidentecho.config import get_settings
from incidentecho.domain.repositories import IncidentRepository, WebhookDeliveryRepository
from incidentecho.github.client import GitHubAppClient, GitHubClient
from incidentecho.persistence.database import SessionFactory, session_scope
from incidentecho.persistence.incidents import SqlAlchemyIncidentRepository
from incidentecho.persistence.webhooks import SqlAlchemyWebhookDeliveryRepository


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
    private_key = settings.github_private_key()
    if settings.github_app_id is None or private_key is None:
        yield None
        return
    async with GitHubAppClient(app_id=settings.github_app_id, private_key=private_key) as client:
        yield client
