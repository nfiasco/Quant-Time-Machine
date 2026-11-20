"""The dependency required by every endpoint serving private account data."""

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.errors import ApiError
from app.auth import (
    AuthServiceUnavailable,
    InvalidAccessToken,
    TokenVerifier,
    UserIdentity,
)

bearer = HTTPBearer(
    auto_error=False,
    scheme_name="SupabaseAccessToken",
    bearerFormat="JWT",
    description="A Supabase user access token, not a publishable or service-role API key.",
)


def current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> UserIdentity:
    """Verify on every protected request; FastAPI runs this sync function in a thread."""
    headers = {"Cache-Control": "private, no-store", "Vary": "Authorization"}
    try:
        if credentials is None or len(request.headers.getlist("authorization")) != 1:
            raise InvalidAccessToken
        verifier: TokenVerifier = request.app.state.token_verifier
        return verifier.verify(credentials.credentials)
    except InvalidAccessToken:
        raise ApiError(
            401,
            "unauthorized",
            "Sign in with a valid access token.",
            headers={**headers, "WWW-Authenticate": "Bearer"},
        ) from None
    except AuthServiceUnavailable:
        raise ApiError(
            503,
            "auth_unavailable",
            "Account verification is temporarily unavailable. Try again later.",
            headers=headers,
        ) from None


CurrentUser = Annotated[UserIdentity, Depends(current_user)]
