"""RecallOps API application factory."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict

from recallops import __version__
from recallops.api.incidents import router as incidents_router
from recallops.config import get_settings
from recallops.persistence.database import create_session_factory


class ServiceStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str
    service: str = "recallops"
    version: str = __version__


async def live() -> ServiceStatus:
    """Report that the process is accepting requests."""

    return ServiceStatus(status="ok")


async def ready() -> ServiceStatus:
    """Report that application initialization completed."""

    return ServiceStatus(status="ready")


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None]:
    """Own database resources for the application lifetime."""

    engine, session_factory = create_session_factory(get_settings().database_url)
    application.state.session_factory = session_factory
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    """Build the HTTP application."""

    application = FastAPI(
        title="RecallOps API",
        summary="Evidence-backed engineering memory for pull-request reviews",
        version=__version__,
        lifespan=lifespan,
    )
    application.include_router(incidents_router)
    application.add_api_route(
        "/health/live", live, response_model=ServiceStatus, tags=["health"], methods=["GET"]
    )
    application.add_api_route(
        "/health/ready", ready, response_model=ServiceStatus, tags=["health"], methods=["GET"]
    )

    return application


app = create_app()
