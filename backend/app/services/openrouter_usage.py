import asyncio
import time
from typing import Any

import httpx

from app.core.config import settings

BASE = "https://openrouter.ai/api/v1"
CACHE_S = 60.0
# ponytail: per-process cache; with several instances each asks OpenRouter once a minute.
_cache: tuple[float, dict[str, Any]] | None = None


def _usd(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return round(float(value), 4)


def _reason(exc: BaseException) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "Timed out"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    return type(exc).__name__


async def _get(http: httpx.AsyncClient, path: str) -> dict[str, Any]:
    r = await http.get(
        f"{BASE}{path}",
        headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}"},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json().get("data")
    return data if isinstance(data, dict) else {}


async def fetch(http: httpx.AsyncClient, *, force: bool = False) -> dict[str, Any]:
    """Account and key figures in USD. A part that fails is null with its reason in `errors`."""
    global _cache
    if not settings.OPENROUTER_API_KEY:
        return {"configured": False, "account": None, "key": None, "errors": {}}
    if not force and _cache and time.monotonic() - _cache[0] < CACHE_S:
        return _cache[1]
    results = await asyncio.gather(
        _get(http, "/credits"), _get(http, "/key"), return_exceptions=True
    )
    credits: dict[str, Any] | BaseException = results[0]
    key_info: dict[str, Any] | BaseException = results[1]
    out: dict[str, Any] = {
        "configured": True,
        "account": None,
        "key": None,
        "errors": {},
    }
    if isinstance(credits, dict):
        bought, used = (
            _usd(credits.get("total_credits")),
            _usd(credits.get("total_usage")),
        )
        if bought is not None and used is not None:
            out["account"] = {
                "credits_usd": bought,
                "used_usd": used,
                "remaining_usd": round(bought - used, 4),
            }
    else:
        out["errors"]["account"] = _reason(credits)
    if isinstance(key_info, dict):
        out["key"] = {
            "used_usd": _usd(key_info.get("usage")),
            "today_usd": _usd(key_info.get("usage_daily")),
            "week_usd": _usd(key_info.get("usage_weekly")),
            "month_usd": _usd(key_info.get("usage_monthly")),
            "limit_usd": _usd(key_info.get("limit")),
        }
    else:
        out["errors"]["key"] = _reason(key_info)
    if out["account"] or out["key"]:  # a total failure is never cached
        _cache = (time.monotonic(), out)
    return out
