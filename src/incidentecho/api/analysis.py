"""Deterministic pull-request analysis endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from incidentecho.api.dependencies import get_incident_repository
from incidentecho.config import get_settings
from incidentecho.domain.models import PullRequestChange, RiskReport
from incidentecho.domain.repositories import IncidentRepository
from incidentecho.services.analysis import CatalogCapacityExceededError, PullRequestAnalysisService

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])
Repository = Annotated[IncidentRepository, Depends(get_incident_repository)]


@router.post("", response_model=RiskReport)
async def analyze_pull_request(
    change: PullRequestChange,
    repository: Repository,
) -> RiskReport:
    """Return explainable historical incident evidence for a proposed change."""

    service = PullRequestAnalysisService(
        repository,
        catalog_limit=get_settings().analysis_catalog_limit,
    )
    try:
        return await service.analyze(change)
    except CatalogCapacityExceededError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Incident catalog exceeds deterministic analysis capacity",
        ) from error
