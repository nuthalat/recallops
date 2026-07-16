"""PostgreSQL integration coverage for the incident adapter."""

import os

import pytest
from sqlalchemy import delete, select

from recallops.domain.models import Incident
from recallops.domain.repositories import IncidentAlreadyExistsError
from recallops.persistence.database import (
    IncidentRecord,
    WebhookDeliveryRecord,
    create_session_factory,
    session_scope,
)
from recallops.persistence.incidents import SqlAlchemyIncidentRepository
from recallops.persistence.webhooks import SqlAlchemyWebhookDeliveryRepository

DATABASE_URL = os.getenv("RECALLOPS_TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.anyio,
    pytest.mark.skipif(DATABASE_URL is None, reason="PostgreSQL integration URL not configured"),
]


async def test_incidents_persist_and_list_in_stable_order() -> None:
    assert DATABASE_URL is not None
    engine, factory = create_session_factory(DATABASE_URL)
    try:
        async with session_scope(factory) as session:
            await session.execute(delete(IncidentRecord))

        older = Incident(incident_id="INC-1", title="Older", summary="First incident")
        newer = Incident(incident_id="INC-2", title="Newer", summary="Second incident")
        async with session_scope(factory) as session:
            repository = SqlAlchemyIncidentRepository(session)
            await repository.add(older)
            await repository.add(newer)

        async with session_scope(factory) as session:
            repository = SqlAlchemyIncidentRepository(session)
            assert await repository.get("INC-1") == older
            listed = await repository.list(limit=10, offset=0)
            assert tuple(item.incident_id for item in listed) == ("INC-2", "INC-1")
    finally:
        await engine.dispose()


async def test_duplicate_identifier_is_a_domain_error() -> None:
    assert DATABASE_URL is not None
    engine, factory = create_session_factory(DATABASE_URL)
    incident = Incident(incident_id="INC-DUP", title="Duplicate", summary="Duplicate test")
    try:
        async with session_scope(factory) as session:
            await session.execute(delete(IncidentRecord))
            repository = SqlAlchemyIncidentRepository(session)
            await repository.add(incident)

        async with session_scope(factory) as session:
            with pytest.raises(IncidentAlreadyExistsError):
                await SqlAlchemyIncidentRepository(session).add(incident)
    finally:
        await engine.dispose()


async def test_unit_of_work_rolls_back_uncaught_errors() -> None:
    assert DATABASE_URL is not None
    engine, factory = create_session_factory(DATABASE_URL)
    incident = Incident(incident_id="INC-ROLLBACK", title="Rollback", summary="Rollback test")
    try:
        with pytest.raises(RuntimeError, match="abort unit of work"):
            async with session_scope(factory) as session:
                await SqlAlchemyIncidentRepository(session).add(incident)
                raise RuntimeError("abort unit of work")

        async with session_scope(factory) as session:
            assert await SqlAlchemyIncidentRepository(session).get(incident.incident_id) is None
    finally:
        await engine.dispose()


async def test_webhook_deliveries_are_idempotent_and_auditable() -> None:
    assert DATABASE_URL is not None
    engine, factory = create_session_factory(DATABASE_URL)
    values = {
        "delivery_id": "delivery-integration",
        "event": "pull_request",
        "action": "opened",
        "payload_sha256": "a" * 64,
        "disposition": "accepted",
    }
    try:
        async with session_scope(factory) as session:
            await session.execute(delete(WebhookDeliveryRecord))
            assert await SqlAlchemyWebhookDeliveryRepository(session).record(**values)

        async with session_scope(factory) as session:
            assert not await SqlAlchemyWebhookDeliveryRepository(session).record(**values)

        async with session_scope(factory) as session:
            record = await session.scalar(select(WebhookDeliveryRecord))
            assert record is not None
            assert record.payload_sha256 == "a" * 64
            assert record.disposition == "accepted"

        async with session_scope(factory) as session:
            await SqlAlchemyWebhookDeliveryRepository(session).discard("delivery-integration")

        async with session_scope(factory) as session:
            assert await session.scalar(select(WebhookDeliveryRecord)) is None
    finally:
        await engine.dispose()
