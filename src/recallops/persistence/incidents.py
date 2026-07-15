"""PostgreSQL-backed incident catalog adapter."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from recallops.domain.models import Incident
from recallops.domain.repositories import IncidentAlreadyExistsError
from recallops.persistence.database import IncidentRecord


class SqlAlchemyIncidentRepository:
    """Persist incidents through one SQLAlchemy unit of work."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, incident: Incident) -> Incident:
        record = IncidentRecord(
            incident_id=incident.incident_id,
            title=incident.title,
            summary=incident.summary,
            affected_paths=list(incident.affected_paths),
            keywords=sorted(incident.keywords),
            source_url=str(incident.source_url) if incident.source_url else None,
        )
        self._session.add(record)
        try:
            await self._session.flush()
        except IntegrityError as error:
            await self._session.rollback()
            raise IncidentAlreadyExistsError(incident.incident_id) from error
        return incident

    async def get(self, incident_id: str) -> Incident | None:
        record = await self._session.get(IncidentRecord, incident_id)
        return _to_domain(record) if record else None

    async def list(self, *, limit: int, offset: int) -> tuple[Incident, ...]:
        statement = (
            select(IncidentRecord)
            .order_by(IncidentRecord.created_at.desc(), IncidentRecord.incident_id.asc())
            .limit(limit)
            .offset(offset)
        )
        records = (await self._session.scalars(statement)).all()
        return tuple(_to_domain(record) for record in records)


def _to_domain(record: IncidentRecord) -> Incident:
    return Incident.model_validate(
        {
            "incident_id": record.incident_id,
            "title": record.title,
            "summary": record.summary,
            "affected_paths": tuple(record.affected_paths),
            "keywords": frozenset(record.keywords),
            "source_url": record.source_url,
        }
    )
