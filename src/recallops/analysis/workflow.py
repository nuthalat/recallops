"""Provider-agnostic contracts for future durable analysis workflows."""

from dataclasses import dataclass, field
from typing import Protocol

from recallops.domain import Evidence, PullRequestChange, RiskReport


@dataclass(slots=True)
class AnalysisState:
    """Mutable state owned by a bounded analysis workflow execution."""

    change: PullRequestChange
    evidence: list[Evidence] = field(default_factory=lambda: list[Evidence]())
    iteration: int = 0
    result: RiskReport | None = None


class WorkflowStep(Protocol):
    """A typed unit of analysis that can later be checkpointed or traced."""

    @property
    def name(self) -> str: ...

    async def execute(self, state: AnalysisState) -> AnalysisState: ...
