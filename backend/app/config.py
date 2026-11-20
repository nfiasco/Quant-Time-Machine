"""Application settings, loaded from environment variables and `backend/.env`.

This is the one place the backend reads API keys and paths. Copy `.env.example` to
`.env` (git-ignored) and fill it in; real environment variables take precedence over
the file. Nothing here is required to run the tests, which use fixtures instead of
live APIs.
"""

from functools import lru_cache
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

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

    # Accounts (D9). S16.4 verifies bearer tokens against this project's JWKS,
    # checking issuer and audience. No service-role key or shared JWT secret needed.
    supabase_url: str | None = None
    supabase_jwt_audience: str = "authenticated"
    # Public key for the Auth /user verification fallback on legacy/local HS256.
    supabase_publishable_key: SecretStr | None = None
    supabase_allow_legacy_hs256: bool = False
    supabase_jwks_cache_seconds: int = Field(default=300, ge=30, le=600)

    @property
    def supabase_jwt_issuer(self) -> str | None:
        return f"{self.supabase_url}/auth/v1" if self.supabase_url else None

    @property
    def supabase_jwks_url(self) -> str | None:
        issuer = self.supabase_jwt_issuer
        return f"{issuer}/.well-known/jwks.json" if issuer else None

    @field_validator("supabase_url")
    @classmethod
    def _validate_supabase_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        url = urlsplit(value)
        local = url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1"}
        if (
            not url.hostname
            or (url.scheme != "https" and not local)
            or url.username
            or url.password
            or url.path not in {"", "/"}
            or url.query
            or url.fragment
        ):
            raise ValueError(
                "SUPABASE_URL must be an HTTPS origin or a local HTTP origin"
            )
        return value.rstrip("/")

    # Raw downloads and the local point-in-time store. Git-ignored.
    # A relative path is resolved from backend/, not from the current directory.
    data_dir: Path = Path("data")

    # Browser origins allowed to call the API (CORS). In the environment, separate them
    # with commas, for example "http://localhost:3000,https://example.vercel.app".
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    # Whether GET /v1/prices serves raw Tiingo prices. Tiingo's terms allow internal use
    # only (D2), so it's off unless turned on, and it stays off on any deployment other
    # people can reach until display rights are settled. Off, the endpoint answers 403.
    serve_raw_prices: bool = False

    # How much memory, in megabytes, the API may use to keep as-of answers, which never
    # change for a data version (app/api/cache.py, S8.6). 0 turns the cache off.
    response_cache_mb: int = Field(default=32, ge=0)

    # The commit the code runs from, which every saved run records (S7.7). Railway sets
    # RAILWAY_GIT_COMMIT_SHA on a deploy from GitHub. Unset, as on a laptop, it's asked
    # of git itself (app/runs.py).
    git_sha: str | None = Field(
        default=None,
        validation_alias=AliasChoices("git_sha", "railway_git_commit_sha"),
    )

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

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        # An origin never ends in a slash, and a browser's Origin header must match exactly.
        if isinstance(value, str):
            value = value.split(",")
        if isinstance(value, list):
            return [
                str(origin).strip().rstrip("/")
                for origin in value
                if str(origin).strip()
            ]
        return value


@lru_cache
def get_settings() -> Settings:
    """Load the settings once per process."""
    return Settings()
