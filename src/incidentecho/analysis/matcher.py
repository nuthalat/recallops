"""Deterministic baseline for linking changed files to historical incidents."""

import re
from fnmatch import fnmatch

from incidentecho.domain import Evidence, Incident, PullRequestChange, RiskLevel, RiskReport

_TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{2,}")


class DeterministicIncidentMatcher:
    """Rank incident evidence without embeddings or model calls.

    Path evidence carries most of the score because it is directly auditable.
    Keyword-only matches require at least two terms, keeping IncidentEcho quiet when
    the available evidence is weak.
    """

    def analyze(
        self,
        change: PullRequestChange,
        incidents: tuple[Incident, ...],
    ) -> RiskReport:
        change_tokens = self._change_tokens(change)
        evidence = tuple(
            sorted(
                filter(
                    None,
                    (self._match(change, change_tokens, incident) for incident in incidents),
                ),
                key=lambda item: (-item.score, item.incident_id),
            )
        )
        highest_score = evidence[0].score if evidence else 0.0
        risk_level = self._risk_level(highest_score)
        summary = (
            "No sufficiently strong historical incident evidence was found."
            if not evidence
            else (
                f"Found {len(evidence)} relevant historical incident(s); review the cited evidence."
            )
        )
        return RiskReport(
            repository=change.repository,
            pull_request_number=change.number,
            risk_level=risk_level,
            evidence=evidence,
            summary=summary,
        )

    def _match(
        self,
        change: PullRequestChange,
        change_tokens: frozenset[str],
        incident: Incident,
    ) -> Evidence | None:
        matched_paths = tuple(
            path
            for path in change.changed_files
            if any(fnmatch(path, pattern) for pattern in incident.affected_paths)
        )
        matched_keywords = tuple(sorted(change_tokens.intersection(incident.keywords)))

        if matched_paths:
            score = min(1.0, 0.7 + (0.1 * min(len(matched_keywords), 3)))
        elif len(matched_keywords) >= 2:
            score = min(0.6, 0.15 * len(matched_keywords))
        else:
            return None

        return Evidence(
            incident_id=incident.incident_id,
            incident_title=incident.title,
            score=round(score, 2),
            matched_paths=matched_paths,
            matched_keywords=matched_keywords,
            source_url=incident.source_url,
        )

    @staticmethod
    def _change_tokens(change: PullRequestChange) -> frozenset[str]:
        content = " ".join((change.title, change.summary, *change.changed_files)).lower()
        return frozenset(_TOKEN_PATTERN.findall(content))

    @staticmethod
    def _risk_level(score: float) -> RiskLevel:
        if score >= 0.8:
            return RiskLevel.HIGH
        if score >= 0.5:
            return RiskLevel.MEDIUM
        if score > 0:
            return RiskLevel.LOW
        return RiskLevel.NONE
