"""Process liveness endpoint."""

import hmac
import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse
from redis import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.auth_limits import redis_client
from app.database import engine
from app.observability import metrics
from app.schemas.health import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness only; dependency checks belong to /ready."""
    return HealthResponse(status="ok")


@router.get("/ready")
def ready():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        client = redis_client()
        if client is not None:
            client.ping()
    except (SQLAlchemyError, RedisError):
        raise HTTPException(503, "Dependencies temporarily unavailable") from None
    return {"status": "ready"}


@router.get("/metrics", include_in_schema=False)
def monitoring(request: Request):
    token = os.environ.get("METRICS_TOKEN", "")
    if not token:
        raise HTTPException(404, "Not found")
    if not hmac.compare_digest(
        request.headers.get("authorization", "").encode(), ("Bearer " + token).encode()
    ):
        raise HTTPException(401, "Monitoring authentication required")
    return PlainTextResponse(metrics.render(), media_type="text/plain; version=0.0.4")
