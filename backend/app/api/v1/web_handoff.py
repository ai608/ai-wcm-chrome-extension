import base64
import hashlib
import hmac

import asyncpg
import jwt
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.api.v1.auth import _user
from app.core.config import settings
from app.core.dependencies import get_user_repository
from app.core.exceptions import AppError
from app.repositories.auth_session_repository import AuthSessionRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import AuthResponse

router = APIRouter(tags=["auth"])


class WebExchangeRequest(BaseModel):
    code: str = Field(min_length=1)
    verifier: str = Field(min_length=43, max_length=128)


@router.post("/auth/web-exchange", response_model=AuthResponse)
async def web_exchange(
    body: WebExchangeRequest,
    request: Request,
    user_repo: UserRepository = Depends(get_user_repository),
) -> AuthResponse:
    if not settings.EXTENSION_HANDOFF_SECRET:
        raise AppError(503, "upstream_error", "Extension sign-in is not configured")
    try:
        claims = jwt.decode(
            body.code,
            settings.EXTENSION_HANDOFF_SECRET,
            algorithms=["HS256"],
            audience="wcm-extension-handoff",
            options={
                "require": [
                    "sub",
                    "jti",
                    "exp",
                    "state",
                    "extension_id",
                    "code_challenge",
                ]
            },
        )
    except jwt.PyJWTError as exc:
        raise AppError(401, "unauthorized", "Sign-in code expired or invalid") from exc
    allowed = {part.strip() for part in settings.EXTENSION_ALLOWED_IDS.split(",")}
    if str(claims["extension_id"]) not in allowed:
        raise AppError(403, "no_extension_access", "Extension is not allowed")
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(body.verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    if not hmac.compare_digest(str(claims["code_challenge"]), challenge):
        raise AppError(401, "unauthorized", "Sign-in request did not match")
    user_id = str(claims["sub"])
    profile = await user_repo.get_by_id(user_id)
    if (
        profile is None
        or not profile.is_active
        or not profile.can_open("chrome_extension")
    ):
        raise AppError(403, "no_extension_access", "Extension access is not enabled")
    pool: asyncpg.Pool = request.app.state.pool
    try:
        access, refresh, expires = await AuthSessionRepository(pool).create(
            user_id, str(claims["jti"])
        )
    except asyncpg.UniqueViolationError as exc:
        raise AppError(401, "unauthorized", "Sign-in code was already used") from exc
    return AuthResponse(
        access_token=access,
        refresh_token=refresh,
        expires_at=expires,
        user=_user(profile),
    )
