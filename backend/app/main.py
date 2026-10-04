"""Application entry point: uvicorn app.main:app."""

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.middleware import RequestGuards

from app.routers.health import router as health_router
from app.routers.items import router as items_router
from app.services.items import ItemStore

app = FastAPI(
    title="Campus Lost-and-Found API",
    description="Report lost and found items. Phase 2 uses temporary in-memory storage.",
    version="0.2.0",
)
app.state.item_store = ItemStore()
app.add_middleware(RequestGuards)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"])
app.include_router(health_router)
app.include_router(items_router)


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
