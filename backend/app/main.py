"""Application entry point: uvicorn app.main:app."""

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from app.routers.health import router as health_router
from app.routers.items import router as items_router
from app.services.items import ItemStore

app = FastAPI(
    title="Campus Lost-and-Found API",
    description="Report lost and found items. Phase 2 uses temporary in-memory storage.",
    version="0.2.0",
)
app.state.item_store = ItemStore()
app.include_router(health_router)
app.include_router(items_router)


@app.get("/", include_in_schema=False)
def documentation() -> RedirectResponse:
    """Send visitors to the interactive API documentation."""
    return RedirectResponse(url="/docs")
