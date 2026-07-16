"""Fail-closed GitHub App installation verification CLI."""

import argparse
import asyncio
from pathlib import Path

from pydantic import SecretStr

from incidentecho.github.client import GitHubAppClient


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--app-id", required=True, type=int)
    result.add_argument("--private-key-file", required=True)
    result.add_argument("--installation-id", required=True, type=int)
    result.add_argument("--app-slug", required=True)
    result.add_argument("--owner", required=True)
    result.add_argument("--repository", required=True)
    return result


async def run(args: argparse.Namespace) -> None:
    private_key = SecretStr(Path(args.private_key_file).read_text())
    async with GitHubAppClient(app_id=args.app_id, private_key=private_key) as client:
        receipt = await client.verify_installation(args.installation_id)
    expected_permissions = {
        "checks": "write",
        "issues": "read",
        "metadata": "read",
        "pull_requests": "read",
    }
    expected_repositories = (f"{args.owner}/{args.repository}",)
    checks = {
        "app slug": receipt.app_slug == args.app_slug,
        "app owner": receipt.app_owner == args.owner,
        "installation account": receipt.installation_account == args.owner,
        "repository selection": receipt.repository_selection == "selected",
        "permissions": dict(receipt.permissions) == expected_permissions,
        "repositories": receipt.repositories == expected_repositories,
    }
    failures = tuple(name for name, passed in checks.items() if not passed)
    if failures:
        raise SystemExit("GitHub App verification failed: " + ", ".join(failures))
    print(f"GitHub App verification passed for {expected_repositories[0]}")
    print(f"app={receipt.app_slug} owner={receipt.app_owner}")
    print(f"installation={receipt.installation_id} selection={receipt.repository_selection}")
    print("permissions=checks:write,issues:read,metadata:read,pull_requests:read")


def main() -> None:
    asyncio.run(run(parser().parse_args()))


if __name__ == "__main__":
    main()
