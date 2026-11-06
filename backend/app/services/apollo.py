"""Apollo organization enrichment: the clinic's size, age, industry and tech stack."""

from typing import Any

import httpx

from app.core.config import settings

URL = "https://api.apollo.io/api/v1/organizations/enrich"


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
        "phone": org.get("phone") or (org.get("primary_phone") or {}).get("number"),
        "address": org.get("raw_address"),
        "employee_count": org.get("estimated_num_employees"),
        "linkedin_url": org.get("linkedin_url"),
        "founded_year": org.get("founded_year"),
        "technologies": org.get("technology_names") or [],
    }
