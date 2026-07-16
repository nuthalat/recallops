"""Database adapters for IncidentEcho."""

from incidentecho.persistence.database import create_session_factory
from incidentecho.persistence.incidents import SqlAlchemyIncidentRepository

__all__ = ["SqlAlchemyIncidentRepository", "create_session_factory"]
