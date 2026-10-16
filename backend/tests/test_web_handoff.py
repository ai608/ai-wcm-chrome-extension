import base64
import hashlib
from datetime import UTC, datetime, timedelta

import asyncpg
import httpx
import jwt
import pytest

from app.core.config import settings
from app.core.dependencies import get_user_repository
from app.main import app
from app.models.user import UserProfile
from app.repositories.auth_session_repository import AuthSessionRepository

EXTENSION_ID = "a" * 32
VERIFIER = "v" * 43
STATE = "s" * 32


def profile(*, access: bool = True) -> UserProfile:
    now = datetime.now(UTC)
    return UserProfile.from_row(
        {
            "id": "user-1",
            "email": "sdr@example.com",
            "full_name": "Sales Rep",
            "role": "user",
            "is_active": True,
            "totp_enabled": False,
            "automation_access": {
                "chrome_extension": {"role": "user"} if access else {"revoked": True}
            },
            "created_at": now,
            "updated_at": now,
        }
    )


class FakeRepo:
    def __init__(self, user: UserProfile) -> None:
        self.user = user

    async def get_by_id(self, user_id: str) -> UserProfile:
        assert user_id == "user-1"
        return self.user


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def code(**overrides: object) -> str:
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    claims = {
        "sub": "user-1",
        "aud": "wcm-extension-handoff",
        "extension_id": EXTENSION_ID,
        "state": STATE,
        "code_challenge": challenge,
        "jti": "one-time-id",
        "exp": datetime.now(UTC) + timedelta(seconds=60),
        **overrides,
    }
    return jwt.encode(claims, settings.EXTENSION_HANDOFF_SECRET, algorithm="HS256")


@pytest.mark.anyio
async def test_exchange_requires_matching_proof_and_rejects_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "EXTENSION_HANDOFF_SECRET", "test-secret-" * 4)
    monkeypatch.setattr(settings, "EXTENSION_ALLOWED_IDS", EXTENSION_ID)
    app.dependency_overrides[get_user_repository] = lambda: FakeRepo(profile())
    used: set[str] = set()

    async def create(
        _self: AuthSessionRepository, _user_id: str, jti: str
    ) -> tuple[str, str, datetime]:
        if jti in used:
            raise asyncpg.UniqueViolationError("replayed")
        used.add(jti)
        return "wcm_at_test", "wcm_rt_test", datetime.now(UTC)

    monkeypatch.setattr(AuthSessionRepository, "create", create)
    app.state.pool = object()
    body = {
        "code": code(),
        "state": STATE,
        "verifier": VERIFIER,
        "extension_id": EXTENSION_ID,
    }
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            mismatch = await client.post(
                "/api/v1/ext/auth/web-exchange", json={**body, "verifier": "x" * 43}
            )
            success = await client.post("/api/v1/ext/auth/web-exchange", json=body)
            replay = await client.post("/api/v1/ext/auth/web-exchange", json=body)
            expired = await client.post(
                "/api/v1/ext/auth/web-exchange",
                json={
                    **body,
                    "code": code(exp=datetime.now(UTC) - timedelta(seconds=1)),
                },
            )
    finally:
        app.dependency_overrides.clear()
    assert mismatch.status_code == 401
    assert success.status_code == 200
    assert success.json()["refresh_token"] == "wcm_rt_test"
    assert replay.status_code == 401
    assert expired.status_code == 401


@pytest.mark.anyio
async def test_exchange_rechecks_grant(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "EXTENSION_HANDOFF_SECRET", "test-secret-" * 4)
    monkeypatch.setattr(settings, "EXTENSION_ALLOWED_IDS", EXTENSION_ID)
    app.dependency_overrides[get_user_repository] = lambda: FakeRepo(
        profile(access=False)
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/ext/auth/web-exchange",
                json={
                    "code": code(),
                    "state": STATE,
                    "verifier": VERIFIER,
                    "extension_id": EXTENSION_ID,
                },
            )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 403
