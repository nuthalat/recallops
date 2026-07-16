"""Tests for bounded, cited GitHub Check output."""

from pydantic import HttpUrl

from incidentecho.domain.models import Evidence, RiskLevel, RiskReport
from incidentecho.github.checks import render_check


def report(*evidence: Evidence, risk_level: RiskLevel = RiskLevel.HIGH) -> RiskReport:
    return RiskReport(
        repository="nuthalat/incidentecho",
        pull_request_number=11,
        risk_level=risk_level,
        evidence=evidence,
        summary="Review the cited historical incident evidence.",
    )


def test_quiet_check_succeeds_without_rendering_uncited_claims() -> None:
    check = render_check(
        report(
            Evidence(
                incident_id="INC-1",
                incident_title="Uncited incident",
                score=0.9,
                matched_paths=("src/api.py",),
            )
        ),
        head_sha="a" * 40,
    )

    assert check.conclusion == "success"
    assert check.title == "No historical incident risk found"
    assert check.text is None


def test_evidence_check_is_neutral_and_links_every_finding() -> None:
    check = render_check(
        report(
            Evidence(
                incident_id="INC-2",
                incident_title="Queue [retry] `storm`",
                score=0.8,
                matched_paths=("src/queue.py",),
                matched_keywords=("retry", "queue"),
                source_url=HttpUrl("https://github.com/nuthalat/incidentecho/issues/2"),
            )
        ),
        head_sha="b" * 40,
    )

    assert check.conclusion == "neutral"
    assert check.title == "High risk: 1 cited incident match(es)"
    assert check.text is not None
    assert "https://github.com/nuthalat/incidentecho/issues/2" in check.text
    assert "Queue \\[retry\\] \\`storm\\`" in check.text
    assert "`src/queue.py`" in check.text


def test_check_output_bounds_large_evidence_sets() -> None:
    evidence = tuple(
        Evidence(
            incident_id=f"INC-{index}",
            incident_title=f"Incident {index}",
            score=0.8,
            source_url=HttpUrl(f"https://example.test/incidents/{index}"),
        )
        for index in range(55)
    )

    check = render_check(report(*evidence), head_sha="c" * 40)

    assert check.text is not None
    assert "5 additional cited match(es) omitted" in check.text
    assert len(check.text) <= 60_000
