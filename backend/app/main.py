"""FastAPI application entry point: creates the app and registers the API routers."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import examples, health, v1
from app.api.cache import ResponseCache
from app.api.errors import InternalErrorMiddleware, add_error_handlers
from app.auth import TokenVerifier
from app.config import Settings, get_settings
from app.run_queue import RunQueue


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """What the server does as it starts and stops, around the app's runs (S8.4).

    A run in the last process stopped with it, so its job is marked failed before the
    first request. That's done here, not in `create_app`: building an app, as a test
    does, must not fail a run that a server on the same data folder has going.
    """
    runs: RunQueue = app.state.run_queue
    runs.recover()
    yield
    runs.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app from `settings`, or from the environment when none are given.

    Handlers read the settings from `app.state.settings` (see `AppSettings` in
    app/api/conventions.py), so a test can build an app with its own.
    """
    if settings is None:
        settings = get_settings()

    app = FastAPI(title="Quant Time Machine API", version="0.1.0", lifespan=_lifespan)
    app.state.settings = settings
    app.state.token_verifier = TokenVerifier(settings)
    # Backtests run in the background, one at a time (app/run_queue.py).
    app.state.run_queue = RunQueue(settings)
    # As-of answers, kept for the store's newest data version (app/api/cache.py). Each
    # app has its own, so a test's app never sees another's answers.
    app.state.response_cache = (
        ResponseCache(settings.response_cache_mb * 1024 * 1024)
        if settings.response_cache_mb
        else None
    )
    # Added before CORS, so CORS wraps it and even a 500 reaches the page readable.
    app.add_middleware(InternalErrorMiddleware)
    # Lets the web app call the API from the browser. Sign-in (E16) sends a bearer
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
