"""Validated domain models for incident evidence and pull-request changes."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class DomainModel(BaseModel):
    """Base model that rejects unexpected fields at system boundaries."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class RiskLevel(StrEnum):
    """Non-blocking risk classification returned by the analysis pipeline."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Incident(DomainModel):
    """A normalized historical production incident."""

    incident_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1)
    affected_paths: tuple[str, ...] = ()
    keywords: frozenset[str] = frozenset()
    source_url: HttpUrl | None = None

    @field_validator("affected_paths")
    @classmethod
    def normalize_paths(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(dict.fromkeys(path.strip().lower() for path in value if path.strip()))

    @field_validator("keywords")
    @classmethod
    def normalize_keywords(cls, value: frozenset[str]) -> frozenset[str]:
        return frozenset(keyword.strip().lower() for keyword in value if keyword.strip())


class PullRequestChange(DomainModel):
    """The minimum pull-request context required for deterministic matching."""

    repository: str = Field(pattern=r"^[^/\s]+/[^/\s]+$")
    number: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=300)
    summary: str = ""
    changed_files: tuple[str, ...] = Field(min_length=1)

    @field_validator("changed_files")
    @classmethod
    def normalize_changed_files(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(dict.fromkeys(path.strip().lower() for path in value if path.strip()))
        if not normalized:
            raise ValueError("changed_files must contain at least one non-empty path")
        return normalized


class Evidence(DomainModel):
    """Explainable evidence connecting an incident to a proposed change."""

    incident_id: str
    incident_title: str
    score: float = Field(ge=0, le=1)
    matched_paths: tuple[str, ...] = ()
    matched_keywords: tuple[str, ...] = ()
    source_url: HttpUrl | None = None


class RiskReport(DomainModel):
    """Deterministic, non-blocking analysis result for a pull request."""

    repository: str
    pull_request_number: int
    risk_level: RiskLevel
    evidence: tuple[Evidence, ...] = ()
    summary: str
