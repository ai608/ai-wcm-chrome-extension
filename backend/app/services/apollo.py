"""Apollo organization enrichment: the clinic's size, age, industry and tech stack."""

import re
from typing import Any

import httpx

from app.core.config import settings

URL = "https://api.apollo.io/api/v1/organizations/enrich"


_UNITS = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}


def money(text: Any) -> int | None:
    """Apollo's printed amount ("500K", "$1.2M", "2.5B") as whole dollars; None if it isn't one."""
    m = re.fullmatch(
        r"\$?\s*([\d.,]+)\s*([KMB])?", str(text or "").strip(), re.IGNORECASE
    )
    if not m:
        return None
    try:
        amount = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    return round(amount * _UNITS.get((m.group(2) or "").upper(), 1)) or None


async def company(http: httpx.AsyncClient, domain: str) -> dict[str, Any] | None:
    """The company card for a website domain, or None when Apollo has no match."""
    r = await http.get(
        URL,
        params={"domain": domain},
        headers={"x-api-key": settings.APOLLO_API_KEY},
        timeout=30,
    )
    r.raise_for_status()
    org = r.json().get("organization") or {}
    if not org:
        return None
    return {
        "name": org.get("name"),
        "description": org.get("short_description") or org.get("seo_description"),
        "industry": org.get("industry"),
        "keywords": (org.get("keywords") or [])[:12],
        "estimated_revenue": org.get("annual_revenue_printed")
        or org.get("organization_revenue_printed"),
        # The number the script's "Annual revenue ($)" field takes.
        "annual_revenue": _dollars(org),
        "phone": org.get("phone") or (org.get("primary_phone") or {}).get("number"),
        "address": org.get("raw_address"),
        "employee_count": org.get("estimated_num_employees"),
        "linkedin_url": org.get("linkedin_url"),
        "founded_year": org.get("founded_year"),
        "technologies": org.get("technology_names") or [],
    }


def _dollars(org: dict[str, Any]) -> int | None:
    exact = org.get("annual_revenue")
    if isinstance(exact, int | float) and not isinstance(exact, bool) and exact > 0:
        return round(exact)
    return money(
        org.get("annual_revenue_printed") or org.get("organization_revenue_printed")
    )
