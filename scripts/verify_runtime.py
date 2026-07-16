"""Exercise the packaged service through its public HTTP contracts."""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE_URL = os.environ.get("INCIDENTECHO_VERIFY_BASE_URL", "http://api:8080")
PHASE = os.environ.get("INCIDENTECHO_VERIFY_PHASE", "initial")
INCIDENT_ID = "VERIFY-INCIDENT-001"


def request_json(method: str, path: str, payload: dict[str, Any] | None = None) -> tuple[int, Any]:
    body = None if payload is None else json.dumps(payload).encode()
    request = Request(
        f"{BASE_URL}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urlopen(request, timeout=10) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"PASS {message}", file=sys.stderr)


def verify_health() -> dict[str, Any]:
    status, body = request_json("GET", "/health/live")
    require(status == 200, "liveness endpoint responds")
    require(body["service"] == "incidentecho", "runtime reports IncidentEcho identity")
    status, ready = request_json("GET", "/health/ready")
    require(status == 200 and ready["status"] == "ready", "readiness endpoint responds")
    return body


def verify_analysis() -> None:
    matched_change = {
        "repository": "incidentecho/canary",
        "number": 101,
        "title": "Adjust payment retry behavior",
        "changed_files": ["src/payments/retry.py"],
    }
    status, matched = request_json("POST", "/api/v1/analysis", matched_change)
    require(status == 200, "matched analysis request succeeds")
    require(matched["risk_level"] == "high", "known incident produces high risk")
    require(matched["evidence"][0]["incident_id"] == INCIDENT_ID, "analysis cites incident")
    require(
        matched["evidence"][0]["source_url"] == "https://example.com/incidents/verify",
        "analysis preserves evidence source",
    )

    quiet_change = {
        "repository": "incidentecho/canary",
        "number": 102,
        "title": "Update unrelated documentation",
        "changed_files": ["docs/style-guide.md"],
    }
    status, quiet = request_json("POST", "/api/v1/analysis", quiet_change)
    require(status == 200, "quiet analysis request succeeds")
    require(quiet["risk_level"] == "none" and quiet["evidence"] == [], "unrelated change is quiet")


def main() -> None:
    health = verify_health()
    if PHASE == "initial":
        incident = {
            "incident_id": INCIDENT_ID,
            "title": "Payment retry storm",
            "summary": "Unbounded retries exhausted payment capacity.",
            "affected_paths": ["src/payments/*.py"],
            "keywords": ["payment", "retry"],
            "source_url": "https://example.com/incidents/verify",
        }
        status, created = request_json("POST", "/api/v1/incidents", incident)
        require(status == 201 and created["incident_id"] == INCIDENT_ID, "incident is persisted")
    elif PHASE == "persistence":
        status, stored = request_json("GET", f"/api/v1/incidents/{INCIDENT_ID}")
        require(status == 200 and stored["incident_id"] == INCIDENT_ID, "incident survives restart")
    else:
        raise ValueError(f"Unknown verification phase: {PHASE}")

    verify_analysis()
    receipt = {
        "schema_version": 1,
        "verified_at": datetime.now(UTC).isoformat(),
        "phase": PHASE,
        "service": health["service"],
        "version": health["version"],
        "checks": {
            "liveness": "pass",
            "readiness": "pass",
            "incident_persistence": "pass",
            "matched_analysis": "pass",
            "quiet_analysis": "pass",
        },
    }
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
