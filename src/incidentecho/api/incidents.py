"""Incident catalog HTTP contracts."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from incidentecho.api.dependencies import get_incident_repository
from incidentecho.domain.models import Incident
from incidentecho.domain.repositories import IncidentAlreadyExistsError, IncidentRepository

router = APIRouter(prefix="/api/v1/incidents", tags=["incidents"])
Repository = Annotated[IncidentRepository, Depends(get_incident_repository)]


@router.post("", response_model=Incident, status_code=status.HTTP_201_CREATED)
async def create_incident(incident: Incident, repository: Repository) -> Incident:
    """Catalog a normalized historical incident."""

    try:
        return await repository.add(incident)
    except IncidentAlreadyExistsError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Incident '{incident.incident_id}' already exists",
        ) from error


@router.get("/{incident_id}", response_model=Incident)
async def get_incident(incident_id: str, repository: Repository) -> Incident:
    """Retrieve one incident by its stable identifier."""

    incident = await repository.get(incident_id)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    return incident


@router.get("", response_model=list[Incident])
async def list_incidents(
    repository: Repository,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> tuple[Incident, ...]:
    """List incidents in stable newest-first order."""

    return await repository.list(limit=limit, offset=offset)
