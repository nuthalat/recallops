"""FastAPI dependency adapters."""

from collections.abc import AsyncIterator
from typing import cast

from fastapi import Request

from recallops.domain.repositories import IncidentRepository
from recallops.persistence.database import SessionFactory, session_scope
from recallops.persistence.incidents import SqlAlchemyIncidentRepository


async def get_incident_repository(request: Request) -> AsyncIterator[IncidentRepository]:
    """Provide one transactional incident repository per request."""

    factory = cast(SessionFactory, request.app.state.session_factory)
    async with session_scope(factory) as session:
        yield SqlAlchemyIncidentRepository(session)
