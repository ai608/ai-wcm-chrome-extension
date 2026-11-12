import hashlib
import secrets
from datetime import timedelta
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.core.dependencies import get_audit_repo, require_extension_access
from app.core.exceptions import AppError
from app.core.rate_limit import rate_limit
from app.models.user import UserProfile
from app.services.audit_runner import fetch_audit

SHARE_DAYS = 7
router = APIRouter(tags=["share"])
public_router = APIRouter(tags=["share"])


class ShareRequest(BaseModel):
    html: str = Field(min_length=1, max_length=8_000_000)


def _hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


@router.post("/research/audits/{audit_id}/share")
async def create_share(
    audit_id: str,
    body: ShareRequest,
    request: Request,
    profile: UserProfile = Depends(require_extension_access),
) -> dict[str, Any]:
    rate_limit(f"share:{profile.id}", 20, 3600)
    await fetch_audit(get_audit_repo(request), audit_id)  # 404 for an unknown audit
    token = secrets.token_urlsafe(32)
    pool: asyncpg.Pool = request.app.state.pool
    async with pool.acquire() as conn:
        expires = await conn.fetchval(
            "INSERT INTO extension.report_shares "
            "(audit_id, token_hash, html, created_by, expires_at) "
            "VALUES ($1, $2, $3, $4, now() + $5) RETURNING expires_at",
            UUID(audit_id),
            _hash(token),
            body.html,
            UUID(profile.id),
            timedelta(days=SHARE_DAYS),
        )
    base = str(request.base_url).rstrip("/")
    return {"url": f"{base}/r/{token}", "expires_at": expires}


@public_router.get("/r/{token}", response_class=HTMLResponse)
async def view_share(token: str, request: Request) -> HTMLResponse:
    pool: asyncpg.Pool = request.app.state.pool
    async with pool.acquire() as conn:
        html = await conn.fetchval(
            "SELECT html FROM extension.report_shares "
            "WHERE token_hash = $1 AND expires_at > now()",
            _hash(token),
        )
    if html is None:
        raise AppError(404, "share_not_found", "This report link has expired")
    return HTMLResponse(
        html,
        headers={
            # Stored HTML is never trusted: no scripts, no network except images.
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; "
            "img-src https: data:; font-src data:; sandbox",
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Robots-Tag": "noindex, nofollow",
        },
    )
