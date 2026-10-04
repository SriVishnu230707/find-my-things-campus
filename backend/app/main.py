"""Application entry point: uvicorn app.main:app."""

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.middleware import RequestGuards

from app.routers.health import router as health_router
from app.routers.items import router as items_router
from contextlib import asynccontextmanager
import logging
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from app.database import engine

@asynccontextmanager
async def lifespan(app):
    try:
        with engine.connect() as connection:
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
            if revision != "0001":
                raise RuntimeError("Database migration required; run alembic upgrade head")
    except SQLAlchemyError:
        raise RuntimeError("Database unavailable or not migrated; run alembic upgrade head") from None
    try:
        yield
    finally:
        engine.dispose()

app = FastAPI(
    title="Campus Lost-and-Found API",
    description="Report lost and found items. Phase 3 stores reports persistently in SQLite.",
    version="0.3.0",
    lifespan=lifespan,
)
app.add_middleware(RequestGuards)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"])
app.include_router(health_router)
app.include_router(items_router)

@app.exception_handler(SQLAlchemyError)
async def database_error(request, error):
    logging.getLogger(__name__).error("Database operation failed (%s)", type(error).__name__)
    return JSONResponse(status_code=503, content={"detail": "Database temporarily unavailable"})


@app.exception_handler(RequestValidationError)
async def validation_error(request, error: RequestValidationError):
    # Do not echo submitted personal information or arbitrarily large inputs.
    details = [{key: value for key, value in issue.items()
                if key in {"type", "loc", "msg"}} for issue in error.errors()]
    return JSONResponse(status_code=422, content={"detail": details})


@app.get("/", include_in_schema=False)
def documentation() -> RedirectResponse:
    """Send visitors to the interactive API documentation."""
    return RedirectResponse(url="/docs")
