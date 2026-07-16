from pydantic import HttpUrl

from incidentecho.analysis import DeterministicIncidentMatcher
from incidentecho.domain import Incident, PullRequestChange, RiskLevel


def test_path_and_keyword_evidence_produces_high_risk_report() -> None:
    change = PullRequestChange(
        repository="acme/payments",
        number=42,
        title="Change payment retry behavior",
        summary="Propagate the idempotency key during retry",
        changed_files=("src/order_processor.py", "config/retry.yaml"),
    )
    incident = Incident(
        incident_id="INC-142",
        title="Duplicate payment events after retry",
        summary="Non-idempotent retries emitted duplicate payment events.",
        affected_paths=("src/order_*.py",),
        keywords=frozenset({"retry", "idempotency", "payment"}),
        source_url=HttpUrl("https://github.com/acme/payments/issues/142"),
    )

    report = DeterministicIncidentMatcher().analyze(change, (incident,))

    assert report.risk_level is RiskLevel.HIGH
    assert report.evidence[0].incident_id == "INC-142"
    assert report.evidence[0].matched_paths == ("src/order_processor.py",)
    assert report.evidence[0].matched_keywords == ("idempotency", "payment", "retry")
    assert report.evidence[0].score == 1.0


def test_single_keyword_without_path_evidence_is_quiet() -> None:
    change = PullRequestChange(
        repository="acme/catalog",
        number=7,
        title="Retry catalog refresh",
        changed_files=("src/catalog.py",),
    )
    incident = Incident(
        incident_id="INC-9",
        title="Payment retry incident",
        summary="A payment retry failed.",
        keywords=frozenset({"retry", "payment"}),
    )

    report = DeterministicIncidentMatcher().analyze(change, (incident,))

    assert report.risk_level is RiskLevel.NONE
    assert report.evidence == ()


def test_keyword_only_evidence_requires_two_terms() -> None:
    change = PullRequestChange(
        repository="acme/payments",
        number=8,
        title="Adjust payment retry settings",
        changed_files=("config/runtime.yaml",),
    )
    incident = Incident(
        incident_id="INC-10",
        title="Retry storm",
        summary="Retries overloaded the payment service.",
        keywords=frozenset({"retry", "payment"}),
    )

    report = DeterministicIncidentMatcher().analyze(change, (incident,))

    assert report.risk_level is RiskLevel.LOW
    assert report.evidence[0].score == 0.3


def test_evidence_is_sorted_by_score_then_incident_id() -> None:
    change = PullRequestChange(
        repository="acme/payments",
        number=9,
        title="Payment retry update",
        changed_files=("src/payments.py",),
    )
    incidents = (
        Incident(
            incident_id="INC-B",
            title="B",
            summary="B",
            affected_paths=("src/*.py",),
        ),
        Incident(
            incident_id="INC-A",
            title="A",
            summary="A",
            affected_paths=("src/*.py",),
        ),
    )

    report = DeterministicIncidentMatcher().analyze(change, incidents)

    assert [item.incident_id for item in report.evidence] == ["INC-A", "INC-B"]
