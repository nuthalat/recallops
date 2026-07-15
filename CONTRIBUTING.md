# Contributing to RecallOps

Thank you for helping make production knowledge reusable.

## Development workflow

1. Start from an issue with explicit acceptance evidence.
2. Create a focused branch.
3. Keep deterministic policy separate from model-assisted reasoning.
4. Add or update tests for every behavior change.
5. Run the quality suite before opening a pull request.

```bash
uv sync --all-groups
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest
docker build -t recallops:local .
```

Pull requests should reference their issue, explain risk and rollback, and call
out architecture decisions that need explicit review.
