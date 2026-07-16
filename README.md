# IncidentEcho

IncidentEcho is an open-source engineering memory platform that helps teams prevent
repeat production failures by bringing evidence from past incidents into pull
request reviews.

The project is intentionally **evidence-first**. Deterministic retrieval and
repository policy remain authoritative; model-assisted reasoning is optional
and must cite the incident evidence behind every recommendation.

## Current status

IncidentEcho is in its foundation stage. The first vertical slice will:

1. ingest incidents stored as Markdown or GitHub issues;
2. inspect files changed by a pull request;
3. find relevant historical incidents;
4. produce a quiet, evidence-backed risk report; and
5. publish that report as a GitHub Check.

The bootstrap implementation currently provides typed domain contracts, a
deterministic incident matcher, health endpoints, and a portable container
development environment.

## Run with Docker

Docker is the only host dependency required for the containerized workflow.

```bash
cp .env.example .env
docker compose up --build
```

Apply database migrations before serving requests in a new environment:

```bash
docker compose run --rm api alembic upgrade head
```

The incident catalog API is available at `/api/v1/incidents` with create, list, and
get-by-ID operations. Incident identifiers are immutable; duplicate identifiers return
HTTP 409 rather than overwriting historical evidence.

Submit a normalized pull-request change to `POST /api/v1/analysis` to receive a
deterministic risk report containing matched paths, matched keywords, scores, and source
links. Analysis is quiet when evidence is weak and returns HTTP 503 rather than silently
analyzing a truncated catalog when `INCIDENTECHO_ANALYSIS_CATALOG_LIMIT` is exceeded.

GitHub can deliver signed events to `POST /api/v1/webhooks/github`. Configure the same
random value in GitHub and `INCIDENTECHO_GITHUB_WEBHOOK_SECRET`. IncidentEcho verifies the
raw-body HMAC-SHA256 signature before parsing or persistence, records only an audit digest,
and deduplicates retries using `X-GitHub-Delivery`. Accepted pull-request events use a
short-lived GitHub App JWT to exchange for an installation token and retrieve every page of
changed files. GitHub API or malformed-context failures return an error and are not recorded
as successful deliveries. The same delivery runs the deterministic incident matcher and
publishes a completed `IncidentEcho incident evidence` Check on the pull request head commit.
Quiet results conclude `success`; cited incident matches conclude `neutral`, so IncidentEcho does
not block a merge without an explicit repository policy. Failed publication releases the
delivery identifier so GitHub can retry safely.

Create a development GitHub App with repository permissions `Pull requests: Read`,
`Issues: Read`, and `Checks: Read and write` (`Metadata: Read` is automatic), subscribe to
pull-request and issue events,
and install it only on the IncidentEcho repository. Set `INCIDENTECHO_GITHUB_APP_ID` and
`INCIDENTECHO_GITHUB_APP_PRIVATE_KEY_FILE` to a read-only mounted PEM path. Inline
`INCIDENTECHO_GITHUB_APP_PRIVATE_KEY` remains available for deployment secret stores and accepts
escaped `\\n` newlines. Never commit the private key, installation token, or webhook secret. Webhook delivery
can remain inactive until this endpoint has a stable HTTPS URL.

Verify the real App installation without printing credentials or installing host tooling:

```bash
INCIDENTECHO_GITHUB_APP_ID=4316536 \
INCIDENTECHO_GITHUB_INSTALLATION_ID=147040451 \
INCIDENTECHO_GITHUB_APP_PRIVATE_KEY_FILE=/absolute/path/to/private-key.pem \
./scripts/verify-github-app.sh
```

The canary fails closed unless the App is owned by `IncidentEcho`, is installed only on
`IncidentEcho/incidentecho`, and has exactly metadata read, issues read, pull requests read,
and checks write.

After the services become healthy:

```bash
curl http://localhost:8080/health/live
curl http://localhost:8080/health/ready
```

Stop the services with `docker compose down`. Add `--volumes` only when you
intend to delete the local IncidentEcho database.

## Verify the packaged system

Run the independent system verifier before a release or infrastructure migration:

```bash
./scripts/verify-system.sh
```

The verifier audits the project identity, builds the production image, builds and
installs the wheel in a clean Python container, migrates an empty PostgreSQL database,
exercises matched and quiet analysis through HTTP, restarts the API, and proves that
incident evidence survives. It writes a machine-readable receipt to
`.artifacts/verification/verification-receipt.json` and tears down its isolated Docker
resources automatically. Docker is the only runtime dependency.

## Native development

IncidentEcho uses Python 3.13 and [uv](https://docs.astral.sh/uv/) for reproducible
dependency management.

```bash
uv sync --all-groups
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run uvicorn incidentecho.api.app:app --reload --port 8080
```

## Design principles

- **Evidence before AI:** recommendations must link to concrete incident data.
- **Quiet by default:** insufficient evidence produces no warning.
- **Humans decide:** models do not independently block merges.
- **Self-hosted first:** code and incident data remain under the operator's control.
- **Provider agnostic:** retrieval and model providers sit behind typed contracts.
- **Open by design:** extension points should be understandable and testable.

## License

IncidentEcho is licensed under the [Apache License 2.0](LICENSE).
