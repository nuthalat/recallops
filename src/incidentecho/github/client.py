"""A small, replaceable GitHub App client."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from typing import Protocol, Self, cast

import httpx
import jwt
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from incidentecho.github.checks import CheckRun


class PullRequestChange(BaseModel):
    """Normalized changed-file evidence returned by GitHub."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    filename: str = Field(min_length=1)
    status: str = Field(min_length=1)
    additions: int = Field(ge=0)
    deletions: int = Field(ge=0)
    changes: int = Field(ge=0)
    patch: str | None = None
    previous_filename: str | None = None


class InstallationVerification(BaseModel):
    """Non-secret facts proven by a GitHub App installation canary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    app_slug: str
    app_owner: str
    installation_id: int
    installation_account: str
    repository_selection: str
    permissions: Mapping[str, str]
    repositories: tuple[str, ...]


class GitHubClient(Protocol):
    """Port used by webhook orchestration and tests."""

    async def pull_request_changes(
        self, *, installation_id: int, owner: str, repository: str, number: int
    ) -> Sequence[PullRequestChange]: ...

    async def publish_check(
        self, *, installation_id: int, owner: str, repository: str, check: CheckRun
    ) -> None: ...


class GitHubAppClient:
    """Authenticate as a GitHub App and retrieve pull-request context."""

    def __init__(
        self,
        *,
        app_id: int,
        private_key: SecretStr,
        http_client: httpx.AsyncClient | None = None,
        now: Callable[[], float] = time.time,
    ) -> None:
        self._app_id = app_id
        self._private_key = private_key
        self._client = http_client or httpx.AsyncClient(
            base_url="https://api.github.com", timeout=15.0
        )
        self._owns_client = http_client is None
        self._now = now

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._owns_client:
            await self._client.aclose()

    def app_jwt(self) -> str:
        """Create a bounded, short-lived RS256 app JWT."""

        issued_at = int(self._now()) - 60
        return jwt.encode(
            {"iat": issued_at, "exp": issued_at + 600, "iss": str(self._app_id)},
            self._private_key.get_secret_value().replace("\\n", "\n"),
            algorithm="RS256",
        )

    async def installation_token(self, installation_id: int) -> SecretStr:
        """Exchange the app JWT for a short-lived installation token."""

        response = await self._client.post(
            f"/app/installations/{installation_id}/access_tokens",
            headers=self._headers(self.app_jwt()),
        )
        response.raise_for_status()
        token = response.json().get("token")
        if not isinstance(token, str) or not token:
            raise ValueError("GitHub installation-token response omitted token")
        return SecretStr(token)

    async def verify_installation(self, installation_id: int) -> InstallationVerification:
        """Return bounded, non-secret installation facts for policy verification."""

        app_response = await self._client.get("/app", headers=self._headers(self.app_jwt()))
        app_response.raise_for_status()
        installation_response = await self._client.get(
            f"/app/installations/{installation_id}", headers=self._headers(self.app_jwt())
        )
        installation_response.raise_for_status()
        token = await self.installation_token(installation_id)
        repositories_response = await self._client.get(
            "/installation/repositories", headers=self._headers(token.get_secret_value())
        )
        repositories_response.raise_for_status()
        app = cast(dict[str, object], app_response.json())
        installation = cast(dict[str, object], installation_response.json())
        repositories = cast(dict[str, object], repositories_response.json())
        owner = cast(dict[str, object], app["owner"])
        account = cast(dict[str, object], installation["account"])
        repository_items = cast(list[dict[str, object]], repositories["repositories"])
        return InstallationVerification(
            app_slug=cast(str, app["slug"]),
            app_owner=cast(str, owner["login"]),
            installation_id=cast(int, installation["id"]),
            installation_account=cast(str, account["login"]),
            repository_selection=cast(str, installation["repository_selection"]),
            permissions=cast(dict[str, str], installation["permissions"]),
            repositories=tuple(cast(str, item["full_name"]) for item in repository_items),
        )

    async def pull_request_changes(
        self, *, installation_id: int, owner: str, repository: str, number: int
    ) -> tuple[PullRequestChange, ...]:
        token = await self.installation_token(installation_id)
        changes: list[PullRequestChange] = []
        page = 1
        while True:
            response = await self._client.get(
                f"/repos/{owner}/{repository}/pulls/{number}/files",
                params={"per_page": 100, "page": page},
                headers=self._headers(token.get_secret_value()),
            )
            response.raise_for_status()
            payload = cast(object, response.json())
            if not isinstance(payload, list):
                raise ValueError("GitHub changed-files response must be a list")
            page_changes = [self._normalize_change(item) for item in cast(list[object], payload)]
            changes.extend(page_changes)
            if len(page_changes) < 100:
                return tuple(changes)
            page += 1

    async def publish_check(
        self, *, installation_id: int, owner: str, repository: str, check: CheckRun
    ) -> None:
        """Publish a completed, non-blocking IncidentEcho Check Run."""

        token = await self.installation_token(installation_id)
        response = await self._client.post(
            f"/repos/{owner}/{repository}/check-runs",
            headers=self._headers(token.get_secret_value()),
            json={
                "name": "IncidentEcho incident evidence",
                "head_sha": check.head_sha,
                "status": "completed",
                "conclusion": check.conclusion,
                "output": {
                    "title": check.title,
                    "summary": check.summary,
                    **({"text": check.text} if check.text is not None else {}),
                },
            },
        )
        response.raise_for_status()

    @staticmethod
    def _headers(token: str) -> Mapping[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    @staticmethod
    def _normalize_change(value: object) -> PullRequestChange:
        if not isinstance(value, dict):
            raise ValueError("GitHub changed-file entry must be an object")
        mapping = cast(dict[str, object], value)
        return PullRequestChange.model_validate(
            {
                key: mapping.get(key)
                for key in (
                    "filename",
                    "status",
                    "additions",
                    "deletions",
                    "changes",
                    "patch",
                    "previous_filename",
                )
                if key in mapping
            }
        )
