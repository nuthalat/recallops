"""Persistence ports owned by the domain layer."""

from typing import Protocol

from recallops.domain.models import Incident


class IncidentAlreadyExistsError(Exception):
    """Raised when an incident identifier is already cataloged."""


class IncidentRepository(Protocol):
    """Storage-independent incident catalog contract."""

    async def add(self, incident: Incident) -> Incident: ...

    async def get(self, incident_id: str) -> Incident | None: ...

    async def list(self, *, limit: int, offset: int) -> tuple[Incident, ...]: ...
