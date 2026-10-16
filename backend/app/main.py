"""Application entry point: uvicorn app.main:app."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.database import engine, verify_database
from app.middleware import RequestGuards
from app.routers.auth import router as auth_router
from app.routers.claims import router as claims_router
from app.routers.health import router as health_router
from app.routers.items import router as items_router
from app.routers.media import router as media_router
from app.routers.notifications import router as notifications_router
from app.security import dummy_hash, signing_secret


@asynccontextmanager
async def lifespan(app):
    try:
        try:
            verify_database(engine)
        except SQLAlchemyError:
            raise RuntimeError(
                "Database unavailable or not migrated; run alembic upgrade head"
            ) from None
        signing_secret()
        dummy_hash()
        yield
    finally:
        engine.dispose()


app = FastAPI(
    title="Campus Lost-and-Found API",
    description="Browse campus reports. Sign in to create reports and manage your own; staff can moderate.",
    version="0.8.0",
    lifespan=lifespan,
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"])
app.add_middleware(RequestGuards)
app.include_router(health_router)
app.include_router(items_router)
app.include_router(auth_router)
app.include_router(claims_router)
app.include_router(media_router)
app.include_router(notifications_router)
app.mount(
    "/campus",
    StaticFiles(directory=Path(__file__).parent / "web", html=True),
    name="campus",
)


@app.exception_handler(SQLAlchemyError)
async def database_error(request, error):
    logging.getLogger(__name__).error(
        "Database operation failed (%s)", type(error).__name__
    )
    return JSONResponse(
        status_code=503, content={"detail": "Database temporarily unavailable"}
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request, error: RequestValidationError):
    # Do not echo submitted personal information or arbitrarily large inputs.
    details = [
        {key: value for key, value in issue.items() if key in {"type", "loc", "msg"}}
        for issue in error.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": details})


@app.get("/", include_in_schema=False)
def documentation() -> RedirectResponse:
    """Send visitors to the interactive API documentation."""
    return RedirectResponse(url="/docs")
