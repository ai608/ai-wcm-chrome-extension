import asyncio
import random
import time
from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import AppError

BASE = "https://services.leadconnectorhq.com"
CATALOG_TTL = 600
_catalog: tuple[float, list[dict[str, Any]]] | None = None
# GHL burst limit is 100 req / 10 s; spec caps concurrency at 5.
_sem = asyncio.Semaphore(5)


def _headers(version: str = "2021-07-28") -> dict[str, str]:
    if not settings.GHL_PIT or not settings.GHL_SALES_LOCATION_ID:
        raise AppError(503, "upstream_error", "GHL is not configured")
    return {
        "Authorization": f"Bearer {settings.GHL_PIT}",
        "Version": version,
        "Accept": "application/json",
    }


async def _call(
    http: httpx.AsyncClient,
    method: str,
    path: str,
    version: str = "2021-07-28",
    **kw: Any,
) -> dict[str, Any]:
    headers = _headers(version)
    for attempt in range(4):
        try:
            async with _sem:
                r = await http.request(
                    method, BASE + path, headers=headers, timeout=10, **kw
                )
        except httpx.HTTPError as exc:
            if attempt == 3:
                raise AppError(502, "upstream_error", "GHL is unavailable") from exc
        else:
            if r.status_code == 404:
                raise AppError(404, "contact_not_found", "Contact not found")
            if r.status_code < 400:
                return r.json() if r.content else {}
            if r.status_code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise AppError(502, "upstream_error", f"GHL error {r.status_code}")
            retry_after = r.headers.get("Retry-After", "")
            if retry_after.isdigit():
                await asyncio.sleep(min(int(retry_after), 5))
                continue
        await asyncio.sleep(2**attempt * 0.3 + random.random() * 0.2)
    raise AppError(502, "upstream_error", "GHL is unavailable")


async def get_catalog(http: httpx.AsyncClient) -> list[dict[str, Any]]:
    """Location custom fields: [{id, fieldKey, dataType, picklistOptions, ...}]."""
    global _catalog
    if _catalog and time.monotonic() - _catalog[0] < CATALOG_TTL:
        return _catalog[1]
    data = await _call(
        http, "GET", f"/locations/{settings.GHL_SALES_LOCATION_ID}/customFields"
    )
    fields: list[dict[str, Any]] = data.get("customFields", [])
    _catalog = (time.monotonic(), fields)
    return fields


async def get_contact(http: httpx.AsyncClient, contact_id: str) -> dict[str, Any]:
    data = await _call(http, "GET", f"/contacts/{contact_id}")
    contact: dict[str, Any] = data.get("contact", data)
    if contact.get("locationId") != settings.GHL_SALES_LOCATION_ID:
        raise AppError(403, "wrong_location", "Contact is in another location")
    return contact


async def contact_website(
    http: httpx.AsyncClient, contact: dict[str, Any]
) -> str | None:
    native = contact.get("website")
    if isinstance(native, str) and native.strip():
        return native.strip()
    fields = contact.get("customFields") or []
    if not isinstance(fields, list):
        return None
    catalog = await get_catalog(http)
    website_ids = {
        field.get("id")
        for field in catalog
        if field.get("fieldKey") == "contact.your_website_url"
    }
    for field in fields:
        if not isinstance(field, dict):
            continue
        if (
            field.get("id") not in website_ids
            and field.get("fieldKey") != "contact.your_website_url"
        ):
            continue
        value = field.get("value")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


async def update_custom_fields(
    http: httpx.AsyncClient, contact_id: str, fields: list[dict[str, Any]]
) -> None:
    await _call(http, "PUT", f"/contacts/{contact_id}", json={"customFields": fields})


async def get_json(
    http: httpx.AsyncClient,
    path: str,
    params: dict[str, Any] | None = None,
    version: str = "2021-07-28",
) -> dict[str, Any]:
    return await _call(http, "GET", path, version=version, params=params)
