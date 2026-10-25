"""FastAPI application entry point: creates the app and registers the API routers."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import examples, health, v1
from app.api.errors import InternalErrorMiddleware, add_error_handlers
from app.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app from `settings`, or from the environment when none are given.

    Handlers read the settings from `app.state.settings` (see `AppSettings` in
    app/api/conventions.py), so a test can build an app with its own.
    """
    if settings is None:
        settings = get_settings()

    app = FastAPI(title="Quant Time Machine API", version="0.1.0")
    app.state.settings = settings
    # Added before CORS, so CORS wraps it and even a 500 reaches the page readable.
    app.add_middleware(InternalErrorMiddleware)
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
    examples.keep_nulls(app)
    return app


app = create_app()
