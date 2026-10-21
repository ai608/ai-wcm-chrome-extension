from fastapi import APIRouter, Depends

from app.core.dependencies import require_extension_access
from app.core.exceptions import AppError

router = APIRouter(dependencies=[Depends(require_extension_access)], tags=["stubs"])


async def unavailable() -> None:
    raise AppError(503, "upstream_error", "This endpoint is not implemented yet")


for method, path in (
    ("POST", "/contacts/{id}/script/regenerate"),
    ("POST", "/contacts/{id}/outcome"),
    ("POST", "/contacts/{id}/enrich"),
    ("GET", "/contacts/{id}/history"),
    ("POST", "/research/audits/{id}/domain-overview"),
    ("POST", "/research/audits/{id}/ai-visibility"),
    ("POST", "/research/audits/{id}/send"),
):
    router.add_api_route(path, unavailable, methods=[method])

webhook_router = APIRouter(tags=["stubs"])
webhook_router.add_api_route(
    "/webhooks/ghl/contact-created", unavailable, methods=["POST"]
)
