"""Tests for GitHub App authentication and PR context retrieval."""

import json

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat
from pydantic import SecretStr

from recallops.github.checks import CheckRun
from recallops.github.client import GitHubAppClient


@pytest.fixture(scope="module")
def private_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def pem(key: rsa.RSAPrivateKey) -> str:
    return key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode()


def test_app_jwt_has_bounded_timestamps_and_app_issuer(
    private_key: rsa.RSAPrivateKey,
) -> None:
    client = GitHubAppClient(
        app_id=1234,
        private_key=SecretStr(pem(private_key).replace("\n", "\\n")),
        now=lambda: 1_700_000_000,
    )

    encoded = client.app_jwt()
    claims = jwt.decode(
        encoded,
        private_key.public_key(),
        algorithms=["RS256"],
        options={"verify_exp": False, "verify_iat": False},
    )

    assert claims == {"iat": 1_699_999_940, "exp": 1_700_000_540, "iss": "1234"}


@pytest.mark.anyio
async def test_owned_http_client_is_closed(private_key: rsa.RSAPrivateKey) -> None:
    client = GitHubAppClient(app_id=1234, private_key=SecretStr(pem(private_key)))

    async with client as entered:
        assert entered is client

    assert client._client.is_closed  # pyright: ignore[reportPrivateUsage]


@pytest.mark.anyio
async def test_retrieves_every_changed_file_page(private_key: rsa.RSAPrivateKey) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/access_tokens"):
            return httpx.Response(201, json={"token": "installation-secret"})
        page = int(request.url.params["page"])
        count = 100 if page == 1 else 1
        return httpx.Response(
            200,
            json=[
                {
                    "sha": "ignored-upstream-field",
                    "filename": f"src/file-{page}-{index}.py",
                    "status": "modified",
                    "additions": 2,
                    "deletions": 1,
                    "changes": 3,
                    "patch": "@@ -1 +1 @@",
                }
                for index in range(count)
            ],
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.github.test"
    ) as http_client:
        client = GitHubAppClient(
            app_id=1234, private_key=SecretStr(pem(private_key)), http_client=http_client
        )
        changes = await client.pull_request_changes(
            installation_id=77, owner="nuthalat", repository="recallops", number=9
        )

    assert len(changes) == 101
    assert changes[-1].filename == "src/file-2-0.py"
    assert requests[0].headers["authorization"].startswith("Bearer ey")
    assert requests[1].headers["authorization"] == "Bearer installation-secret"
    assert requests[2].url.params["page"] == "2"


@pytest.mark.anyio
async def test_api_failure_is_not_converted_to_success(private_key: rsa.RSAPrivateKey) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "installation suspended"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.github.test"
    ) as http_client:
        client = GitHubAppClient(
            app_id=1234, private_key=SecretStr(pem(private_key)), http_client=http_client
        )
        with pytest.raises(httpx.HTTPStatusError):
            await client.installation_token(77)


@pytest.mark.anyio
async def test_malformed_changed_file_is_rejected(private_key: rsa.RSAPrivateKey) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(201, json={"token": "installation-secret"})
        return httpx.Response(200, content=json.dumps([{"filename": "missing-fields.py"}]))

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.github.test"
    ) as http_client:
        client = GitHubAppClient(
            app_id=1234, private_key=SecretStr(pem(private_key)), http_client=http_client
        )
        with pytest.raises(ValueError):
            await client.pull_request_changes(
                installation_id=77, owner="nuthalat", repository="recallops", number=9
            )


@pytest.mark.anyio
@pytest.mark.parametrize("payload", [{}, {"token": ""}])
async def test_missing_installation_token_is_rejected(
    private_key: rsa.RSAPrivateKey, payload: dict[str, str]
) -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(201, json=payload))
    async with httpx.AsyncClient(
        transport=transport, base_url="https://api.github.test"
    ) as http_client:
        client = GitHubAppClient(
            app_id=1234, private_key=SecretStr(pem(private_key)), http_client=http_client
        )
        with pytest.raises(ValueError, match="omitted token"):
            await client.installation_token(77)


@pytest.mark.anyio
@pytest.mark.parametrize("files_payload", [{"not": "a list"}, ["not an object"]])
async def test_malformed_changed_files_response_is_rejected(
    private_key: rsa.RSAPrivateKey, files_payload: object
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return (
            httpx.Response(201, json={"token": "installation-secret"})
            if calls == 1
            else httpx.Response(200, json=files_payload)
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.github.test"
    ) as http_client:
        client = GitHubAppClient(
            app_id=1234, private_key=SecretStr(pem(private_key)), http_client=http_client
        )
        with pytest.raises(ValueError):
            await client.pull_request_changes(
                installation_id=77, owner="nuthalat", repository="recallops", number=9
            )


@pytest.mark.anyio
async def test_publishes_completed_check_with_installation_token(
    private_key: rsa.RSAPrivateKey,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return (
            httpx.Response(201, json={"token": "installation-secret"})
            if request.url.path.endswith("/access_tokens")
            else httpx.Response(201, json={"id": 123})
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.github.test"
    ) as http_client:
        client = GitHubAppClient(
            app_id=1234, private_key=SecretStr(pem(private_key)), http_client=http_client
        )
        await client.publish_check(
            installation_id=77,
            owner="nuthalat",
            repository="recallops",
            check=CheckRun(
                head_sha="a" * 40,
                conclusion="neutral",
                title="Historical incident evidence found",
                summary="Review the cited incident.",
            ),
        )

    payload = json.loads(requests[-1].content)
    assert requests[-1].headers["authorization"] == "Bearer installation-secret"
    assert payload["head_sha"] == "a" * 40
    assert payload["status"] == "completed"
    assert payload["conclusion"] == "neutral"
    assert "text" not in payload["output"]
