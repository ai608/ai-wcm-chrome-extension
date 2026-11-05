import json

import httpx
import pytest

from app.core.config import settings
from app.services import openrouter_usage as ou

pytestmark = pytest.mark.anyio

SECRET = "sk-or-v1-supersecretkeymaterial"
CREDITS = {"data": {"total_credits": 85, "total_usage": 74.719768608}}
KEY = {
    "data": {
        "label": "sk-or-v1-fc8...497",  # partial key text: must never be passed on
        "usage": 28.523099978,
        "usage_daily": 4.90071625,
        "usage_weekly": 11.224666808,
        "usage_monthly": 11.224666808,
        "limit": 250,
        "creator_user_id": "user_x",
    }
}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _fresh(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", SECRET)
    monkeypatch.setattr(ou, "_cache", None)


def client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_returns_balance_left_and_this_keys_usage_without_any_key_text():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.headers["authorization"] == f"Bearer {SECRET}"
        return httpx.Response(
            200, json=CREDITS if req.url.path.endswith("/credits") else KEY
        )

    async with client(handler) as http:
        out = await ou.fetch(http)
    assert out["account"] == {
        "credits_usd": 85.0,
        "used_usd": 74.7198,
        "remaining_usd": 10.2802,
    }
    assert out["key"] == {
        "used_usd": 28.5231,
        "today_usd": 4.9007,
        "week_usd": 11.2247,
        "month_usd": 11.2247,
        "limit_usd": 250.0,
    }
    assert out["errors"] == {} and out["configured"] is True
    dumped = json.dumps(out)
    assert "sk-or" not in dumped and "creator" not in dumped and "label" not in dumped


async def test_one_part_failing_keeps_the_other_and_says_why():
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/credits"):
            return httpx.Response(403, text=f"forbidden {SECRET}")
        return httpx.Response(200, json=KEY)

    async with client(handler) as http:
        out = await ou.fetch(http)
    assert out["account"] is None and out["errors"] == {"account": "HTTP 403"}
    assert out["key"]["used_usd"] == 28.5231
    assert SECRET not in json.dumps(out)


async def test_not_configured_makes_no_call_and_a_total_failure_is_not_cached():
    calls = []

    def boom(req: httpx.Request) -> httpx.Response:
        calls.append(req.url.path)
        return httpx.Response(500)

    async with client(boom) as http:
        assert (await ou.fetch(http))["errors"] == {
            "account": "HTTP 500",
            "key": "HTTP 500",
        }
        await ou.fetch(http)  # failed answers are asked again, not served from cache
    assert len(calls) == 4

    settings.OPENROUTER_API_KEY = ""
    async with client(boom) as http:
        assert (await ou.fetch(http))["configured"] is False
    assert len(calls) == 4


async def test_answers_are_cached_for_a_minute_and_refresh_skips_the_cache():
    n = 0

    def handler(req: httpx.Request) -> httpx.Response:
        nonlocal n
        n += 1
        return httpx.Response(
            200, json=CREDITS if req.url.path.endswith("/credits") else KEY
        )

    async with client(handler) as http:
        await ou.fetch(http)
        await ou.fetch(http)
        assert n == 2  # one pair of calls for two asks
        await ou.fetch(http, force=True)
        assert n == 4
