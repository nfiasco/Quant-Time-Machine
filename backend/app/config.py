"""Application settings, loaded from environment variables and `backend/.env`.

This is the one place the backend reads API keys and paths. Copy `.env.example` to
`.env` (git-ignored) and fill it in; real environment variables take precedence over
the file. Nothing here is required to run the tests, which use fixtures instead of
live APIs.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Anchored to backend/ so it is found no matter which directory the app starts in.
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        # A blank line such as `FRED_API_KEY=` means "not set", not an empty key.
        env_ignore_empty=True,
        # .env may hold variables that only scripts use (for example, the price spike's keys).
        extra="ignore",
    )

    # FRED/ALFRED API key (free): https://fredaccount.stlouisfed.org/apikeys
    fred_api_key: SecretStr | None = None

    # SEC asks automated clients to identify themselves: a name plus a contact email,
    # for example "Quant Time Machine (UD CISC 498) jdoe@udel.edu".
    sec_user_agent: str | None = None

    # Tiingo API token for daily prices (decision D2): https://www.tiingo.com/account/api/token
    tiingo_api_key: SecretStr | None = None

    # Raw downloads and the local point-in-time store. Git-ignored.
    # A relative path is resolved from backend/, not from the current directory.
    data_dir: Path = Path("data")

    @field_validator("sec_user_agent")
    @classmethod
    def _require_contact_email(cls, value: str | None) -> str | None:
        if value is not None and "@" not in value:
            raise ValueError("SEC_USER_AGENT must include a contact email address")
        return value

    @field_validator("data_dir")
    @classmethod
    def _resolve_data_dir(cls, value: Path) -> Path:
        value = value.expanduser()
        return value if value.is_absolute() else BACKEND_DIR / value


@lru_cache
def get_settings() -> Settings:
    """Load the settings once per process."""
    return Settings()
