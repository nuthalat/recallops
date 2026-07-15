"""Idempotent GitHub webhook delivery persistence."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from recallops.persistence.database import WebhookDeliveryRecord


class SqlAlchemyWebhookDeliveryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        delivery_id: str,
        event: str,
        action: str | None,
        payload_sha256: str,
        disposition: str,
    ) -> bool:
        self._session.add(
            WebhookDeliveryRecord(
                delivery_id=delivery_id,
                event=event,
                action=action,
                payload_sha256=payload_sha256,
                disposition=disposition,
            )
        )
        try:
            await self._session.flush()
        except IntegrityError:
            await self._session.rollback()
            return False
        return True
