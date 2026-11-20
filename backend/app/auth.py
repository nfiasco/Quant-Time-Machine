"""Supabase access-token verification (D9, S16.4).

Only public signing keys are cached, never tokens or user identities. The sync
FastAPI dependency runs network/key verification in a worker thread. URLs come
from application settings, never token headers such as jku or x5u.
"""

from typing import Any
from uuid import UUID

import httpx2
import jwt
from pydantic import BaseModel, ConfigDict

from app.config import Settings

ASYMMETRIC_ALGORITHMS = ("ES256", "RS256")
REQUIRED_CLAIMS = ["exp", "iss", "aud", "sub", "role"]
MAX_TOKEN_LENGTH = 16_384
AUTH_TIMEOUT_SECONDS = 5


class InvalidAccessToken(Exception):
    """A missing, malformed, expired, or untrusted user token."""


class AuthServiceUnavailable(Exception):
    """Verification cannot finish because configuration or Auth is unavailable."""


class UserIdentity(BaseModel):
    """The verified subject available to private handlers, with no credentials."""

    model_config = ConfigDict(frozen=True)
    user_id: UUID


class TokenVerifier:
    """One verifier per app, with a bounded, thread-safe public JWKS cache."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.jwks = (
            jwt.PyJWKClient(
                settings.supabase_jwks_url,
                cache_keys=False,  # Individual-key LRU entries would never expire.
                lifespan=settings.supabase_jwks_cache_seconds,
                timeout=AUTH_TIMEOUT_SECONDS,
                cooldown_duration=30,
            )
            if settings.supabase_jwks_url
            else None
        )

    def verify(self, token: str) -> UserIdentity:
        if not token or len(token) > MAX_TOKEN_LENGTH:
            raise InvalidAccessToken
        try:
            header = jwt.get_unverified_header(token)
            algorithm = header.get("alg")
            if header.get("crit"):
                raise InvalidAccessToken  # No critical JWT extensions are supported.
            if algorithm == "HS256":
                if not self.settings.supabase_allow_legacy_hs256:
                    raise InvalidAccessToken
                return self._verify_legacy(token)
            if algorithm not in ASYMMETRIC_ALGORITHMS:
                raise InvalidAccessToken
            kid = header.get("kid")
            if not isinstance(kid, str) or not kid or len(kid) > 256:
                raise InvalidAccessToken
            if self.jwks is None:
                raise AuthServiceUnavailable
            key = self.jwks.get_signing_key(kid)
            if key.algorithm_name != algorithm:
                raise InvalidAccessToken
            claims = jwt.decode(
                token,
                key.key,
                algorithms=list(ASYMMETRIC_ALGORITHMS),
                issuer=self.settings.supabase_jwt_issuer,
                audience=self.settings.supabase_jwt_audience,
                options={"require": REQUIRED_CLAIMS},
            )
            return self._identity(claims)
        except jwt.PyJWKClientConnectionError:
            raise AuthServiceUnavailable from None
        except jwt.PyJWKError, jwt.PyJWKSetError:
            raise AuthServiceUnavailable from None
        except jwt.PyJWTError, ValueError, TypeError, OverflowError:
            raise InvalidAccessToken from None

    @staticmethod
    def _identity(claims: dict[str, Any]) -> UserIdentity:
        if claims.get("role") != "authenticated" or claims.get("is_anonymous") is True:
            raise InvalidAccessToken
        # JWT NumericDate is a JSON number, not a string or bool.
        if type(claims.get("exp")) not in (int, float):
            raise InvalidAccessToken
        return UserIdentity(user_id=UUID(claims["sub"]))

    def _verify_legacy(self, token: str) -> UserIdentity:
        key = self.settings.supabase_publishable_key
        if not self.settings.supabase_url or not key:
            raise AuthServiceUnavailable
        # These unverified claims can reject a token early, but cannot authorize it.
        # Auth /user must independently verify its HS256 signature below.
        claims = jwt.decode(
            token,
            options={
                "verify_signature": False,
                "verify_exp": True,
                "verify_nbf": True,
                "verify_iat": True,
                "verify_aud": True,
                "verify_iss": True,
                "verify_sub": True,
                "require": REQUIRED_CLAIMS,
            },
            issuer=self.settings.supabase_jwt_issuer,
            audience=self.settings.supabase_jwt_audience,
        )
        candidate = self._identity(claims)
        try:
            response = httpx2.get(
                f"{self.settings.supabase_url}/auth/v1/user",
                headers={
                    "apikey": key.get_secret_value(),
                    "Authorization": f"Bearer {token}",
                },
                timeout=AUTH_TIMEOUT_SECONDS,
                follow_redirects=False,
            )
            if response.status_code in (401, 403):
                raise InvalidAccessToken
            if response.status_code != 200:
                raise AuthServiceUnavailable
            user = response.json()
            if not isinstance(user, dict) or user.get("id") != str(candidate.user_id):
                raise InvalidAccessToken
        except httpx2.HTTPError, ValueError:
            raise AuthServiceUnavailable from None
        return candidate
