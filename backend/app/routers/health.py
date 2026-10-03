"""Process liveness endpoint."""

from fastapi import APIRouter

from app.schemas.health import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Confirm the API can respond; no database is connected in Phase 1."""
    return HealthResponse(status="ok")
