from pathlib import Path

import pytest
from pydantic import SecretStr

from incidentecho.config import Settings


def test_reads_private_key_from_file(tmp_path: Path) -> None:
    key_file = tmp_path / "app.pem"
    key_file.write_text("secret-pem")

    key = Settings(github_app_private_key_file=key_file).github_private_key()

    assert key is not None
    assert key.get_secret_value() == "secret-pem"


def test_rejects_two_private_key_sources(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="only one"):
        Settings(
            github_app_private_key=SecretStr("inline"),
            github_app_private_key_file=tmp_path / "app.pem",
        ).github_private_key()


def test_missing_private_key_is_disabled() -> None:
    assert Settings().github_private_key() is None
