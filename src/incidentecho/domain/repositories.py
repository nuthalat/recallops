"""Persistence ports owned by the domain layer."""

from typing import Protocol

from incidentecho.domain.models import Incident


class IncidentAlreadyExistsError(Exception):
    """Raised when an incident identifier is already cataloged."""


class IncidentRepository(Protocol):
    """Storage-independent incident catalog contract."""

    async def add(self, incident: Incident) -> Incident: ...

    async def get(self, incident_id: str) -> Incident | None: ...

    async def list(self, *, limit: int, offset: int) -> tuple[Incident, ...]: ...


class WebhookDeliveryRepository(Protocol):
    """Idempotent audit store for external webhook deliveries."""

    async def record(
        self,
        *,
        delivery_id: str,
        event: str,
        action: str | None,
        payload_sha256: str,
        disposition: str,
    ) -> bool: ...

    async def discard(self, delivery_id: str) -> None: ...
