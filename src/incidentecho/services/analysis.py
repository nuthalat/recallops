"""Use case for analyzing proposed changes against incident history."""

from incidentecho.analysis import DeterministicIncidentMatcher
from incidentecho.domain.models import PullRequestChange, RiskReport
from incidentecho.domain.repositories import IncidentRepository


class CatalogCapacityExceededError(Exception):
    """Raised rather than silently analyzing a truncated incident catalog."""


class PullRequestAnalysisService:
    """Coordinate bounded incident retrieval and deterministic analysis."""

    def __init__(
        self,
        repository: IncidentRepository,
        *,
        catalog_limit: int,
        matcher: DeterministicIncidentMatcher | None = None,
    ) -> None:
        self._repository = repository
        self._catalog_limit = catalog_limit
        self._matcher = matcher or DeterministicIncidentMatcher()

    async def analyze(self, change: PullRequestChange) -> RiskReport:
        incidents = await self._repository.list(limit=self._catalog_limit + 1, offset=0)
        if len(incidents) > self._catalog_limit:
            raise CatalogCapacityExceededError
        return self._matcher.analyze(change, incidents)
