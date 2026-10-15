# Copied from AI Lead Pipeline backend app/core/dependencies.py, trimmed for the Sales Assistant.
from typing import Any

import asyncpg
import httpx
import jwt
from fastapi import Depends, Request

from app.core.exceptions import AppError
from app.core.security import verify_token
from app.models.user import UserProfile
from app.repositories.user_repository import UserRepository


def get_user_repository(request: Request) -> UserRepository:
    pool: asyncpg.Pool | None = getattr(request.app.state, "pool", None)
    if pool is None:
        raise AppError(503, "upstream_error", "Database is not configured")
    return UserRepository(pool)


def get_http_client(request: Request) -> httpx.AsyncClient:
    client: httpx.AsyncClient | None = getattr(request.app.state, "http_client", None)
    if client is None:
        raise AppError(503, "upstream_error", "HTTP client is not available")
    return client


async def get_current_user(request: Request) -> dict[str, Any]:
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AppError(401, "unauthorized", "Authorization required")
    try:
        return verify_token(token.strip())
    except jwt.ExpiredSignatureError as exc:
        raise AppError(401, "token_expired", "Token expired") from exc
    except (jwt.PyJWTError, ValueError) as exc:
        raise AppError(401, "unauthorized", "Invalid token") from exc


async def get_current_user_profile(
    current_user: dict[str, Any] = Depends(get_current_user),
    user_repo: UserRepository = Depends(get_user_repository),
) -> UserProfile:
    user_id = current_user.get("sub")
    if not isinstance(user_id, str) or not user_id:
        raise AppError(401, "unauthorized", "Invalid token")
    profile = await user_repo.get_by_id(user_id)
    if profile is None or not profile.is_active:
        raise AppError(403, "no_extension_access", "Account is not active")
    return profile


async def require_extension_access(
    profile: UserProfile = Depends(get_current_user_profile),
) -> UserProfile:
    if not profile.can_open("chrome_extension"):
        raise AppError(403, "no_extension_access", "Extension access is not enabled")
    return profile
