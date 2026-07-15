# RecallOps

RecallOps is an open-source engineering memory platform that helps teams prevent
repeat production failures by bringing evidence from past incidents into pull
request reviews.

The project is intentionally **evidence-first**. Deterministic retrieval and
repository policy remain authoritative; model-assisted reasoning is optional
and must cite the incident evidence behind every recommendation.

## Current status

RecallOps is in its foundation stage. The first vertical slice will:

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

After the services become healthy:

```bash
curl http://localhost:8080/health/live
curl http://localhost:8080/health/ready
```

Stop the services with `docker compose down`. Add `--volumes` only when you
intend to delete the local RecallOps database.

## Native development

RecallOps uses Python 3.13 and [uv](https://docs.astral.sh/uv/) for reproducible
dependency management.

```bash
uv sync --all-groups
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run uvicorn recallops.api.app:app --reload --port 8080
```

## Design principles

- **Evidence before AI:** recommendations must link to concrete incident data.
- **Quiet by default:** insufficient evidence produces no warning.
- **Humans decide:** models do not independently block merges.
- **Self-hosted first:** code and incident data remain under the operator's control.
- **Provider agnostic:** retrieval and model providers sit behind typed contracts.
- **Open by design:** extension points should be understandable and testable.

## License

RecallOps is licensed under the [Apache License 2.0](LICENSE).
