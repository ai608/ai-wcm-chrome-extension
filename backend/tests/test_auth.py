import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import httpx
import jwt
import pyotp
import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import ec

from app.api.v1 import auth
from app.core import dependencies, rate_limit, security
from app.core.config import settings
from app.core.dependencies import get_http_client, get_user_repository
from app.core.encryption import decrypt_value
from app.main import app
from app.models.user import UserProfile


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def profile(
    *, active: bool = True, access: bool = True, totp: bool = False
) -> UserProfile:
    now = datetime.now(UTC)
    return UserProfile.from_row(
        {
            "id": "user-1",
            "email": "sdr@example.com",
            "full_name": "Sales Rep",
            "role": "user",
            "is_active": active,
            "totp_enabled": totp,
            "automation_access": {
                "chrome_extension": {"role": "user"} if access else {"revoked": True}
            },
            "created_at": now,
            "updated_at": now,
        }
    )


class FakeRepo:
    def __init__(self, user: UserProfile | None, secret: str | None = None) -> None:
        self.user = user
        self.secret = secret

    async def get_by_id(self, user_id: str) -> UserProfile | None:
        assert user_id == "user-1"
        return self.user

    async def get_totp_secret(self, user_id: str) -> str | None:
        assert user_id == "user-1"
        return self.secret


@pytest.fixture
def auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://supabase.test")
    monkeypatch.setattr(settings, "SUPABASE_PUBLISHABLE_KEY", "publishable")
    monkeypatch.setattr(auth, "verify_token", lambda _token: {"sub": "user-1"})
    monkeypatch.setattr(dependencies, "verify_token", lambda _token: {"sub": "user-1"})
    rate_limit._hits.clear()
    yield
    app.dependency_overrides.clear()
    rate_limit._hits.clear()


def client_for(
    repo: FakeRepo, handler: Any
) -> tuple[httpx.AsyncClient, httpx.AsyncClient]:
    supabase = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    app.dependency_overrides[get_user_repository] = lambda: repo
    app.dependency_overrides[get_http_client] = lambda: supabase
    api = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )
    return api, supabase


def grant(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/auth/v1/logout":
        return httpx.Response(204)
    assert request.headers["apikey"] == "publishable"
    assert request.url.path == "/auth/v1/token"
    return httpx.Response(
        200,
        json={
            "access_token": "access",
            "refresh_token": "refresh",
            "expires_at": 1790000000,
        },
    )


@pytest.mark.anyio
async def test_login_without_totp_and_no_access(auth_env: None) -> None:
    for access in (True, False):
        api, supabase = client_for(FakeRepo(profile(access=access)), grant)
        async with api, supabase:
            response = await api.post(
                "/api/v1/ext/auth/login",
                json={"email": "sdr@example.com", "password": "secret"},
            )
        assert response.status_code == 200
        body = response.json()
        assert body["access_token"] == "access"
        assert body["refresh_token"] == "refresh"
        assert body["expires_at"].endswith("Z")
        assert body["user"]["has_extension_access"] is access


@pytest.mark.anyio
async def test_totp_required_invalid_and_valid(auth_env: None) -> None:
    secret = pyotp.random_base32()
    api, supabase = client_for(FakeRepo(profile(totp=True), secret), grant)
    async with api, supabase:
        no_code = await api.post(
            "/api/v1/ext/auth/login", json={"email": "a", "password": "b"}
        )
        bad_code = await api.post(
            "/api/v1/ext/auth/login",
            json={"email": "a", "password": "b", "totp_code": "not-a-code"},
        )
        good_code = await api.post(
            "/api/v1/ext/auth/login",
            json={"email": "a", "password": "b", "totp_code": pyotp.TOTP(secret).now()},
        )
    assert no_code.status_code == 401
    assert no_code.json()["error"]["code"] == "totp_required"
    assert bad_code.json()["error"]["code"] == "invalid_totp"
    assert good_code.status_code == 200


@pytest.mark.anyio
async def test_invalid_password_and_inactive_profile(auth_env: None) -> None:
    api, supabase = client_for(FakeRepo(profile()), lambda _r: httpx.Response(400))
    async with api, supabase:
        denied = await api.post(
            "/api/v1/ext/auth/login", json={"email": "a", "password": "b"}
        )
    assert denied.json()["error"]["code"] == "invalid_credentials"

    for user in (profile(active=False), None):
        api, supabase = client_for(FakeRepo(user), grant)
        async with api, supabase:
            denied_profile = await api.post(
                "/api/v1/ext/auth/login", json={"email": "a", "password": "b"}
            )
        assert denied_profile.status_code == 403
        assert denied_profile.json()["error"]["code"] == "no_extension_access"


@pytest.mark.anyio
async def test_refresh_logout_me_and_stub_gate(auth_env: None) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return grant(request)

    api, supabase = client_for(FakeRepo(profile()), handler)
    async with api, supabase:
        refreshed = await api.post(
            "/api/v1/ext/auth/refresh", json={"refresh_token": "old"}
        )
        me = await api.get("/api/v1/ext/me", headers={"Authorization": "Bearer access"})
        stub = await api.get(
            "/api/v1/ext/research/audits/latest",
            headers={"Authorization": "Bearer access"},
        )
        logged_out = await api.post(
            "/api/v1/ext/auth/logout", headers={"Authorization": "Bearer access"}
        )
    assert refreshed.status_code == 200
    assert json.loads(seen[0].content)["refresh_token"] == "old"
    assert me.json()["has_extension_access"] is True
    assert stub.status_code == 503
    assert stub.json()["error"]["code"] == "upstream_error"
    assert logged_out.status_code == 204
    assert seen[-1].headers["Authorization"] == "Bearer access"


@pytest.mark.anyio
async def test_refresh_failure_and_bearer_errors(
    auth_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    api, supabase = client_for(FakeRepo(profile()), lambda _r: httpx.Response(401))
    async with api, supabase:
        failed = await api.post(
            "/api/v1/ext/auth/refresh", json={"refresh_token": "expired"}
        )
        missing = await api.get("/api/v1/ext/me")
        monkeypatch.setattr(
            dependencies,
            "verify_token",
            lambda _token: (_ for _ in ()).throw(jwt.ExpiredSignatureError()),
        )
        expired = await api.get(
            "/api/v1/ext/me", headers={"Authorization": "Bearer old"}
        )
    assert failed.json()["error"]["code"] == "unauthorized"
    assert missing.json()["error"]["code"] == "unauthorized"
    assert expired.json()["error"]["code"] == "token_expired"


@pytest.mark.anyio
async def test_revoked_user_cannot_use_stubs(auth_env: None) -> None:
    api, supabase = client_for(FakeRepo(profile(access=False)), grant)
    async with api, supabase:
        response = await api.get(
            "/api/v1/ext/config", headers={"Authorization": "Bearer access"}
        )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "no_extension_access"


def test_decrypt_copied_fernet_format(monkeypatch: pytest.MonkeyPatch) -> None:
    key = Fernet.generate_key()
    monkeypatch.setattr(settings, "ENCRYPTION_KEY", key.decode())
    assert (
        decrypt_value("enc:" + Fernet(key).encrypt(b"TOTPSECRET").decode())
        == "TOTPSECRET"
    )


def test_verify_copied_es256_jwt(monkeypatch: pytest.MonkeyPatch) -> None:
    private = ec.generate_private_key(ec.SECP256R1())
    token = jwt.encode(
        {
            "sub": "user-1",
            "aud": "authenticated",
            "exp": int(datetime.now(UTC).timestamp()) + 3600,
        },
        private,
        algorithm="ES256",
    )
    monkeypatch.setattr(
        security,
        "_get_jwks_client",
        lambda: SimpleNamespace(
            get_signing_key_from_jwt=lambda _token: SimpleNamespace(
                key=private.public_key()
            )
        ),
    )
    assert security.verify_token(token)["sub"] == "user-1"


def test_login_rate_limit_with_fake_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.exceptions import AppError

    rate_limit._hits.clear()
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: 100.0)
    for _ in range(10):
        rate_limit.rate_limit("login:ip:email", 10, 60)
    with pytest.raises(AppError) as exc:
        rate_limit.rate_limit("login:ip:email", 10, 60)
    assert exc.value.code == "rate_limited"
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: 161.0)
    rate_limit.rate_limit("login:ip:email", 10, 60)
