from typing import Any

import asyncpg
import httpx
from fastapi import APIRouter, Depends, Request

from app.core.dependencies import get_http_client, require_extension_access
from app.core.exceptions import AppError
from app.models.user import UserProfile
from app.repositories.history_repository import HistoryBriefRepository
from app.services import history

router = APIRouter(tags=["history"])


def get_brief_repository(request: Request) -> HistoryBriefRepository:
    pool: asyncpg.Pool | None = getattr(request.app.state, "pool", None)
    if pool is None:
        raise AppError(503, "upstream_error", "Database is not configured")
    return HistoryBriefRepository(pool)


@router.get("/contacts/{contact_id}/history")
async def get_history(
    contact_id: str,
    profile: UserProfile = Depends(require_extension_access),
    http: httpx.AsyncClient = Depends(get_http_client),
    repo: HistoryBriefRepository = Depends(get_brief_repository),
) -> dict[str, Any]:
    return await history.get_history(http, repo, contact_id, profile.id)
