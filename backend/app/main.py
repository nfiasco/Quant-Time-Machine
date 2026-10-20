"""FastAPI application entry point: creates the app and registers the API routers."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health, v1
from app.api.conventions import add_error_handlers
from app.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app from `settings`, or from the environment when none are given."""
    if settings is None:
        settings = get_settings()

    app = FastAPI(title="Quant Time Machine API", version="0.1.0")
    # Lets the web app call the API from the browser. Sign-in (E16) will send a bearer
    # token, not cookies, so credentialed requests stay off.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )
    add_error_handlers(app)

    app.include_router(health.router)
    app.include_router(v1.router)
    return app


app = create_app()
