from argparse import Namespace
from pathlib import Path

import pytest

from incidentecho.github import verify
from incidentecho.github.client import InstallationVerification


class FakeClient:
    receipt = InstallationVerification(
        app_slug="incidentecho-dev",
        app_owner="IncidentEcho",
        installation_id=77,
        installation_account="IncidentEcho",
        repository_selection="selected",
        permissions={
            "checks": "write",
            "issues": "read",
            "metadata": "read",
            "pull_requests": "read",
        },
        repositories=("IncidentEcho/incidentecho",),
    )

    def __init__(self, **_: object) -> None:
        pass

    async def __aenter__(self) -> "FakeClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        pass

    async def verify_installation(self, _: int) -> InstallationVerification:
        return self.receipt


def arguments(key_file: Path) -> Namespace:
    return Namespace(
        app_id=1234,
        private_key_file=str(key_file),
        installation_id=77,
        app_slug="incidentecho-dev",
        owner="IncidentEcho",
        repository="incidentecho",
    )


@pytest.mark.anyio
async def test_canary_passes_without_printing_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    key_file = tmp_path / "app.pem"
    key_file.write_text("private-key-material")
    monkeypatch.setattr(verify, "GitHubAppClient", FakeClient)

    await verify.run(arguments(key_file))

    output = capsys.readouterr().out
    assert "verification passed" in output
    assert "private-key-material" not in output


@pytest.mark.anyio
async def test_canary_fails_closed_on_repository_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key_file = tmp_path / "app.pem"
    key_file.write_text("private-key-material")
    monkeypatch.setattr(verify, "GitHubAppClient", FakeClient)
    original = FakeClient.receipt
    FakeClient.receipt = original.model_copy(update={"repositories": ("IncidentEcho/other",)})
    try:
        with pytest.raises(SystemExit, match="repositories"):
            await verify.run(arguments(key_file))
    finally:
        FakeClient.receipt = original


def test_parser_requires_all_policy_inputs() -> None:
    with pytest.raises(SystemExit):
        verify.parser().parse_args([])
