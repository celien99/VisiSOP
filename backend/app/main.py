import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path

import contracts.demo  # noqa: F401  (registers the demo event catalog)
import sentry_sdk
from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.middleware.cors import CORSMiddleware

from app.api.main import api_router
from app.application.outbox_dispatcher import run_outbox_dispatcher
from app.core.config import settings

FRONTEND_DIR = Path(__file__).parent / "frontend"


def custom_generate_unique_id(route: APIRoute) -> str:
    return f"{route.tags[0]}-{route.name}"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # shortcut: in-process dispatcher; move to a dedicated worker with multiple API workers.
    tasks: list[asyncio.Task[None]] = []
    if settings.WORKERS_ENABLED:
        tasks.append(asyncio.create_task(run_outbox_dispatcher()))
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task


if settings.SENTRY_DSN:
    sentry_sdk.init(dsn=str(settings.SENTRY_DSN), enable_tracing=True)

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_PREFIX}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_HOST],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_PREFIX)
app.frontend("/", directory=FRONTEND_DIR)
