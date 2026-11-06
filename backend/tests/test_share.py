import hashlib
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from app.api.v1 import share
from app.core.dependencies import require_extension_access
from app.main import app
from app.models.user import UserProfile

pytestmark = pytest.mark.anyio
AUDIT = str(uuid.uuid4())


class Conn:
    def __init__(self, rows: dict[bytes, tuple[str, datetime]]) -> None:
        self.rows = rows

    async def fetchval(self, sql: str, *args: Any) -> Any:
        if sql.startswith("INSERT"):
            _audit, token_hash, html, _user, ttl = args
            expires = datetime.now(UTC) + ttl
            self.rows[token_hash] = (html, expires)
            return expires
        html, expires = self.rows.get(args[0], (None, None))
        return html if expires and expires > datetime.now(UTC) else None


class Pool:
    def __init__(self) -> None:
        self.rows: dict[bytes, tuple[str, datetime]] = {}

    @asynccontextmanager
    async def acquire(self):  # type: ignore[no-untyped-def]
        yield Conn(self.rows)


class Repo:
    async def get(self, audit_id: str) -> object | None:
        return object() if audit_id == AUDIT else None


@pytest.fixture
async def api(monkeypatch):  # type: ignore[no-untyped-def]
    now = datetime.now(UTC)
    app.dependency_overrides[require_extension_access] = lambda: UserProfile(
        id=str(uuid.uuid4()),
        email="a@b.co",
        full_name="A",
        avatar_url=None,
        role="user",
        is_active=True,
        admin_id=None,
        created_at=now,
        updated_at=now,
    )
    pool = Pool()
    monkeypatch.setattr(app.state, "pool", pool, raising=False)
    monkeypatch.setattr(share, "_repo", lambda _request: Repo())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as c:
        yield c, pool
    app.dependency_overrides.clear()


async def test_link_serves_report_for_seven_days_then_expires(api) -> None:  # type: ignore[no-untyped-def]
    c, pool = api
    r = await c.post(
        f"/api/v1/ext/research/audits/{AUDIT}/share", json={"html": "<p>Report</p>"}
    )
    assert r.status_code == 200
    url = r.json()["url"]
    assert url.startswith("http://t/r/")
    token = url.rsplit("/", 1)[1]
    key = hashlib.sha256(token.encode()).digest()
    html, expires = pool.rows[key]
    assert html == "<p>Report</p>" and token not in html
    assert timedelta(days=6, hours=23) < expires - datetime.now(UTC) <= timedelta(days=7)

    page = await c.get(f"/r/{token}")
    assert page.status_code == 200 and page.text == "<p>Report</p>"
    assert "sandbox" in page.headers["content-security-policy"]

    pool.rows[key] = (html, datetime.now(UTC) - timedelta(seconds=1))
    assert (await c.get(f"/r/{token}")).status_code == 404
    assert (await c.get("/r/unknown")).status_code == 404


async def test_unknown_audit_gets_no_link(api) -> None:  # type: ignore[no-untyped-def]
    c, _ = api
    r = await c.post(
        f"/api/v1/ext/research/audits/{uuid.uuid4()}/share", json={"html": "x"}
    )
    assert r.status_code == 404
