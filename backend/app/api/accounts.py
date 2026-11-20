"""Private account endpoints. Deliberately excluded from the as-of response cache."""

from fastapi import APIRouter, Response

from app.api.auth import CurrentUser
from app.api.errors import ErrorResponse
from app.auth import UserIdentity

router = APIRouter(tags=["accounts"])


@router.get(
    "/me",
    responses={
        401: {
            "model": ErrorResponse,
            "description": "A user access token is missing or invalid",
        },
        503: {
            "model": ErrorResponse,
            "description": "Account verification is unavailable",
        },
    },
)
def get_current_account(user: CurrentUser, response: Response) -> UserIdentity:
    """Return the verified caller's ID. No token, email, or user metadata is echoed."""
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Vary"] = "Authorization"
    return user
