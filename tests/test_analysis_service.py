import pytest

from incidentecho.domain.models import Incident, PullRequestChange, RiskLevel
from incidentecho.domain.repositories import IncidentAlreadyExistsError
from incidentecho.services.analysis import CatalogCapacityExceededError, PullRequestAnalysisService


class StubRepository:
    def __init__(self, incidents: tuple[Incident, ...]) -> None:
        self.incidents = incidents

    async def add(self, incident: Incident) -> Incident:
        raise IncidentAlreadyExistsError

    async def get(self, incident_id: str) -> Incident | None:
        return None

    async def list(self, *, limit: int, offset: int) -> tuple[Incident, ...]:
        return self.incidents[offset : offset + limit]


@pytest.mark.anyio
async def test_service_analyzes_persisted_incident_evidence() -> None:
    incident = Incident(
        incident_id="INC-1",
        title="Checkout retry incident",
        summary="Retries duplicated checkout requests.",
        affected_paths=("src/checkout/*.py",),
        keywords=frozenset({"checkout", "retry"}),
    )
    change = PullRequestChange(
        repository="acme/shop",
        number=12,
        title="Adjust checkout retry",
        changed_files=("src/checkout/service.py",),
    )

    report = await PullRequestAnalysisService(
        StubRepository((incident,)), catalog_limit=10
    ).analyze(change)

    assert report.risk_level is RiskLevel.HIGH
    assert report.evidence[0].matched_paths == ("src/checkout/service.py",)


@pytest.mark.anyio
async def test_service_rejects_truncated_catalog() -> None:
    incidents = tuple(
        Incident(incident_id=f"INC-{index}", title="Incident", summary="Summary")
        for index in range(3)
    )
    change = PullRequestChange(
        repository="acme/shop", number=1, title="Change", changed_files=("src/app.py",)
    )

    with pytest.raises(CatalogCapacityExceededError):
        await PullRequestAnalysisService(StubRepository(incidents), catalog_limit=2).analyze(change)
