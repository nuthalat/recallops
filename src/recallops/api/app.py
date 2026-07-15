"""Application entry point with dependency-free health contracts."""

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict

from recallops import __version__


class ServiceStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str
    service: str = "recallops"
    version: str = __version__


app = FastAPI(
    title="RecallOps API",
    summary="Evidence-backed engineering memory for pull-request reviews",
    version=__version__,
)


@app.get("/health/live", response_model=ServiceStatus, tags=["health"])
async def live() -> ServiceStatus:
    """Report that the process is accepting requests."""

    return ServiceStatus(status="ok")


@app.get("/health/ready", response_model=ServiceStatus, tags=["health"])
async def ready() -> ServiceStatus:
    """Report bootstrap readiness; dependency checks arrive with their adapters."""

    return ServiceStatus(status="ready")
