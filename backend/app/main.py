"""Application entry point: uvicorn app.main:app."""

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from app.routers.health import router as health_router

app = FastAPI(
    title="Campus Lost-and-Found API",
    description="Phase 1 foundation. Report management will be added in Phase 2.",
    version="0.1.0",
)
app.include_router(health_router)


@app.get("/", include_in_schema=False)
def documentation() -> RedirectResponse:
    """Send visitors to the interactive API documentation."""
    return RedirectResponse(url="/docs")
