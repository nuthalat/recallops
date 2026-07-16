"""Bounded, evidence-backed GitHub Check output."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from incidentecho.domain.models import RiskReport

_MAX_SUMMARY_LENGTH = 60_000
_MAX_TEXT_LENGTH = 60_000
_MAX_RENDERED_EVIDENCE = 50


class CheckRun(BaseModel):
    """Completed Check Run content accepted by GitHub."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    head_sha: str = Field(min_length=7, max_length=64)
    conclusion: Literal["success", "neutral"]
    title: str = Field(min_length=1, max_length=255)
    summary: str = Field(min_length=1, max_length=_MAX_SUMMARY_LENGTH)
    text: str | None = Field(default=None, max_length=_MAX_TEXT_LENGTH)


def render_check(report: RiskReport, *, head_sha: str) -> CheckRun:
    """Render only cited incident evidence, keeping output within GitHub limits."""

    cited = tuple(evidence for evidence in report.evidence if evidence.source_url is not None)
    conclusion: Literal["success", "neutral"] = "success" if not cited else "neutral"
    title = (
        "No historical incident risk found"
        if not cited
        else f"{report.risk_level.value.title()} risk: {len(cited)} cited incident match(es)"
    )
    summary = report.summary if cited else "No cited historical incident evidence was found."
    lines = ["## Historical incident evidence", ""]
    for evidence in cited[:_MAX_RENDERED_EVIDENCE]:
        source_url = str(evidence.source_url)
        lines.extend(
            (
                f"### [{_escape(evidence.incident_title)}]({source_url})",
                f"Score: `{evidence.score:.2f}`",
                _detail("Matched paths", evidence.matched_paths),
                _detail("Matched keywords", evidence.matched_keywords),
                "",
            )
        )
    omitted = len(cited) - _MAX_RENDERED_EVIDENCE
    if omitted > 0:
        lines.append(f"_{omitted} additional cited match(es) omitted to bound check output._")
    return CheckRun(
        head_sha=head_sha,
        conclusion=conclusion,
        title=title,
        summary=summary[:_MAX_SUMMARY_LENGTH],
        text="\n".join(lines)[:_MAX_TEXT_LENGTH] if cited else None,
    )


def _detail(label: str, values: tuple[str, ...]) -> str:
    rendered = ", ".join(f"`{_escape(value)}`" for value in values) if values else "None"
    return f"**{label}:** {rendered}"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("`", "\\`").replace("[", "\\[").replace("]", "\\]")
