from fastapi import APIRouter, Depends

from app.core.dependencies import require_extension_access
from app.core.exceptions import AppError

router = APIRouter(dependencies=[Depends(require_extension_access)], tags=["stubs"])


async def unavailable() -> None:
    raise AppError(503, "upstream_error", "This endpoint is not implemented yet")


for method, path in (
    ("GET", "/config"),
    ("GET", "/script"),
    ("GET", "/contacts/{id}/context"),
    ("GET", "/contacts/{id}/script"),
    ("POST", "/contacts/{id}/script/regenerate"),
    ("PATCH", "/contacts/{id}/fields"),
    ("POST", "/contacts/{id}/outcome"),
    ("POST", "/contacts/{id}/enrich"),
    ("GET", "/contacts/{id}/history"),
    ("GET", "/contacts/{id}/research"),
    ("POST", "/contacts/{id}/research"),
    ("POST", "/research/audits"),
    ("GET", "/research/audits/latest"),
    ("GET", "/research/audits/{id}"),
    ("POST", "/research/audits/{id}/domain-overview"),
    ("POST", "/research/audits/{id}/local-competitors"),
    ("POST", "/research/audits/{id}/ai-visibility"),
    ("GET", "/research/audits/{id}/report"),
    ("POST", "/research/audits/{id}/send"),
):
    router.add_api_route(path, unavailable, methods=[method])

webhook_router = APIRouter(tags=["stubs"])
webhook_router.add_api_route(
    "/webhooks/ghl/contact-created", unavailable, methods=["POST"]
)
