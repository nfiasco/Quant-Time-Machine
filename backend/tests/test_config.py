from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import BACKEND_DIR, Settings

ENV_VARS = ("FRED_API_KEY", "SEC_USER_AGENT", "TIINGO_API_KEY", "DATA_DIR")


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    # Keep a developer's real keys out of these tests. Each test also passes
    # _env_file=None (or its own file) so backend/.env is never read.
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_defaults_need_no_keys() -> None:
    settings = Settings(_env_file=None)

    assert settings.fred_api_key is None
    assert settings.sec_user_agent is None
    assert settings.tiingo_api_key is None
    assert settings.data_dir == BACKEND_DIR / "data"


def test_environment_variables_override_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("FRED_API_KEY", "test-key")
    monkeypatch.setenv("SEC_USER_AGENT", "Quant Time Machine test@example.com")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    settings = Settings(_env_file=None)

    assert settings.fred_api_key is not None
    assert settings.fred_api_key.get_secret_value() == "test-key"
    assert settings.sec_user_agent == "Quant Time Machine test@example.com"
    assert settings.data_dir == tmp_path


def test_api_keys_are_masked_when_printed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRED_API_KEY", "fred-test-key")
    monkeypatch.setenv("TIINGO_API_KEY", "tiingo-test-key")

    settings = Settings(_env_file=None)

    for secret in ("fred-test-key", "tiingo-test-key"):
        assert secret not in repr(settings)
        assert secret not in str(settings)
    assert settings.tiingo_api_key is not None
    assert settings.tiingo_api_key.get_secret_value() == "tiingo-test-key"


def test_relative_data_dir_resolves_from_backend(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATA_DIR", "./store")

    settings = Settings(_env_file=None)

    assert settings.data_dir == BACKEND_DIR / "store"


def test_env_file_ignores_blank_and_unknown_values(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "FRED_API_KEY=\n"
        "TIINGO_API_KEY=only-used-by-a-spike\n"
        'SEC_USER_AGENT="Quant Time Machine test@example.com"\n'
    )

    settings = Settings(_env_file=env_file)

    assert settings.fred_api_key is None
    assert settings.sec_user_agent == "Quant Time Machine test@example.com"


def test_sec_user_agent_requires_contact_email(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEC_USER_AGENT", "Quant Time Machine")

    with pytest.raises(ValidationError, match="contact email"):
        Settings(_env_file=None)


def test_env_file_is_anchored_to_backend() -> None:
    assert Settings.model_config["env_file"] == BACKEND_DIR / ".env"
