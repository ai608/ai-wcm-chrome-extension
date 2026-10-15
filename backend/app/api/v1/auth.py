# Copied from AI Lead Pipeline backend app/api/v1/auth.py, trimmed for the Sales Assistant.
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt
from fastapi import APIRouter, Depends, Request, Response

from app.core.config import settings
from app.core.dependencies import (
    get_current_user_profile,
    get_http_client,
    get_user_repository,
)
from app.core.exceptions import AppError
from app.core.rate_limit import rate_limit
from app.core.security import verify_token
from app.models.user import UserProfile
from app.repositories.user_repository import UserRepository
from app.schemas.auth import AuthResponse, LoginRequest, RefreshRequest, UserResponse
from app.services.totp import verify_code

router = APIRouter(tags=["auth"])


def _supabase_headers() -> dict[str, str]:
    if not settings.SUPABASE_URL or not settings.SUPABASE_PUBLISHABLE_KEY:
        raise AppError(503, "upstream_error", "Supabase is not configured")
    return {
        "apikey": settings.SUPABASE_PUBLISHABLE_KEY,
        "Content-Type": "application/json",
    }


def _user(profile: UserProfile) -> UserResponse:
    return UserResponse(
        id=profile.id,
        email=profile.email,
        full_name=profile.full_name or "",
        role=profile.role,  # type: ignore[arg-type]
        has_extension_access=profile.can_open("chrome_extension"),
    )


def _auth_response(tokens: dict[str, Any], profile: UserProfile) -> AuthResponse:
    try:
        if tokens.get("expires_at") is not None:
            expires = datetime.fromtimestamp(int(tokens["expires_at"]), tz=UTC)
        else:
            expires = datetime.now(UTC) + timedelta(seconds=int(tokens["expires_in"]))
        return AuthResponse(
            access_token=tokens["access_token"],
            refresh_token=tokens["refresh_token"],
            expires_at=expires,
            user=_user(profile),
        )
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise AppError(
            502, "upstream_error", "Invalid Supabase token response"
        ) from exc


def _tokens(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise AppError(
            502, "upstream_error", "Invalid Supabase token response"
        ) from exc
    if not isinstance(payload, dict):
        raise AppError(502, "upstream_error", "Invalid Supabase token response")
    return payload


async def _profile_from_token(
    tokens: dict[str, Any], user_repo: UserRepository
) -> UserProfile:
    try:
        payload = verify_token(tokens["access_token"])
        user_id = payload["sub"]
        if not isinstance(user_id, str) or not user_id:
            raise ValueError("Token has no subject")
    except (KeyError, jwt.PyJWTError, ValueError) as exc:
        raise AppError(502, "upstream_error", "Invalid Supabase access token") from exc
    profile = await user_repo.get_by_id(user_id)
    if profile is None or not profile.is_active:
        raise AppError(403, "no_extension_access", "Account is not active")
    return profile


@router.post("/auth/login", response_model=AuthResponse)
async def login(
    body: LoginRequest,
    request: Request,
    user_repo: UserRepository = Depends(get_user_repository),
    client: httpx.AsyncClient = Depends(get_http_client),
) -> AuthResponse:
    ip = request.client.host if request.client else "unknown"
    rate_limit(f"login:{ip}:{body.email.strip().lower()}", 10, 60)
    try:
        supabase_resp = await client.post(
            f"{settings.SUPABASE_URL}/auth/v1/token",
            params={"grant_type": "password"},
            headers=_supabase_headers(),
            json={"email": body.email, "password": body.password},
        )
    except httpx.HTTPError as exc:
        raise AppError(503, "upstream_error", "Supabase is unavailable") from exc
    if supabase_resp.status_code != 200:
        raise AppError(401, "invalid_credentials", "Invalid email or password")
    tokens = _tokens(supabase_resp)
    profile = await _profile_from_token(tokens, user_repo)
    if profile.totp_enabled:
        if not body.totp_code:
            raise AppError(401, "totp_required", "Authentication code required")
        secret = await user_repo.get_totp_secret(profile.id)
        if secret is None or not verify_code(secret, body.totp_code):
            raise AppError(401, "invalid_totp", "Invalid authentication code")
    return _auth_response(tokens, profile)


@router.post("/auth/refresh", response_model=AuthResponse)
async def refresh(
    body: RefreshRequest,
    user_repo: UserRepository = Depends(get_user_repository),
    client: httpx.AsyncClient = Depends(get_http_client),
) -> AuthResponse:
    try:
        supabase_resp = await client.post(
            f"{settings.SUPABASE_URL}/auth/v1/token",
            params={"grant_type": "refresh_token"},
            headers=_supabase_headers(),
            json={"refresh_token": body.refresh_token},
        )
        if supabase_resp.status_code != 200:
            raise AppError(401, "unauthorized", "Session expired")
        tokens = _tokens(supabase_resp)
        profile = await _profile_from_token(tokens, user_repo)
        return _auth_response(tokens, profile)
    except (httpx.HTTPError, jwt.PyJWTError, ValueError, AppError) as exc:
        raise AppError(401, "unauthorized", "Session expired") from exc


@router.post("/auth/logout", status_code=204)
async def logout(
    request: Request,
    client: httpx.AsyncClient = Depends(get_http_client),
) -> Response:
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() == "bearer" and token.strip() and settings.SUPABASE_URL:
        try:
            await client.post(
                f"{settings.SUPABASE_URL}/auth/v1/logout",
                headers={
                    **_supabase_headers(),
                    "Authorization": f"Bearer {token.strip()}",
                },
            )
        except (httpx.HTTPError, AppError):
            pass
    return Response(status_code=204)


@router.get("/me", response_model=UserResponse)
async def get_me(
    profile: UserProfile = Depends(get_current_user_profile),
) -> UserResponse:
    return _user(profile)
