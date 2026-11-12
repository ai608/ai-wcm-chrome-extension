"""Local competitor search (Apify Google Maps) for an audited clinic."""

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.core.config import settings
from app.core.exceptions import AppError
from app.repositories.audit_repository import AuditRepository, to_wire
from app.services import site_audit
from app.services.audit_runner import domain_of, fetch_audit


def _now() -> str:
    return datetime.now(UTC).isoformat()


# ponytail: one radius for every clinic; make it per market if suburbs and cities need different reach.
CLINIC_RADIUS_KM = 8


async def _apify_places(
    http: httpx.AsyncClient,
    query: str,
    location: str,
    near: tuple[float, float] | None = None,
) -> list[dict[str, Any]]:
    """Google Maps results for `query`: around the clinic's coordinates when given (what a
    patient close to the clinic sees), else around the typed city. Apify ignores
    customGeolocation when a location text is sent, so only one of the two goes in."""
    body: dict[str, Any] = {
        "searchStringsArray": [query],
        "maxCrawledPlacesPerSearch": 20,
        "language": "en",
    }
    if near:
        body["customGeolocation"] = {
            "type": "Point",
            "coordinates": [near[1], near[0]],  # longitude first
            "radiusKm": CLINIC_RADIUS_KM,
        }
    else:
        body["locationQuery"] = location
    r = await http.post(
        f"https://api.apify.com/v2/acts/{settings.APIFY_GMAPS_ACTOR_ID}/run-sync-get-dataset-items",
        params={"token": settings.APIFY_API_TOKEN},
        json=body,
        timeout=90,
    )
    if r.status_code >= 400:
        raise AppError(
            502, "upstream_error", f"Competitor search failed ({r.status_code})"
        )
    items = r.json()
    return items if isinstance(items, list) else []


def _clinic_point(gbp: dict[str, Any]) -> tuple[float, float] | None:
    lat, lng = gbp.get("lat"), gbp.get("lng")
    if isinstance(lat, int | float) and isinstance(lng, int | float):
        return float(lat), float(lng)
    return None


async def search(
    repo: AuditRepository,
    http: httpx.AsyncClient,
    audit_id: str,
    query_text: str | None,
    location_text: str | None,
) -> dict[str, Any]:
    """Run the search, save the result in the audit's research section, return the audit."""
    audit = to_wire(await fetch_audit(repo, audit_id))
    research = audit.get("research") or site_audit.empty_research()
    services = ((audit.get("site") or {}).get("services") or {}).get("clusters") or []
    query = (query_text or (services[0]["service"] if services else "med spa")).strip()
    location = (location_text or "").strip()
    gbp = (audit.get("business") or {}).get("gbp") or {}
    # No typed place and the clinic's coordinates are known: search around the clinic.
    near = None if location else _clinic_point(gbp)
    if near:
        address = str(gbp.get("address") or "the clinic")
        location = f"within {CLINIC_RADIUS_KM} km of {address}"
    if not settings.APIFY_API_TOKEN or not settings.APIFY_GMAPS_ACTOR_ID:
        result: dict[str, Any] = {
            "state": "failed",
            "data": None,
            "ran_at": _now(),
            "error": "Local competitor search is not set up yet (APIFY_API_TOKEN).",
        }
    elif not location:
        result = {
            "state": "failed",
            "data": None,
            "ran_at": _now(),
            "error": "Enter a city or area to search near.",
        }
    else:
        try:
            places = await _apify_places(http, query, location, near)
            items = []
            clinic_id = gbp.get("place_id")
            for rank, p in enumerate(places[:20], 1):
                site = p.get("website") or None
                host = domain_of(urlsplit(site).hostname or "") if site else ""
                # The Google listing id is exact; the website is the backup when it is unknown.
                same_id = bool(clinic_id) and p.get("placeId") == clinic_id
                items.append(
                    {
                        "rank": rank,
                        "name": str(p.get("title") or ""),
                        "rating": p.get("totalScore"),
                        "review_count": p.get("reviewsCount"),
                        "website": site,
                        "is_this_business": same_id
                        or (bool(host) and host == audit["domain"]),
                    }
                )
            result = {
                "state": "ready",
                "error": None,
                "ran_at": _now(),
                "data": {"query": query, "location": location, "items": items},
            }
        except (AppError, httpx.HTTPError, ValueError) as exc:
            message = (
                exc.message if isinstance(exc, AppError) else "Competitor search failed"
            )
            result = {
                "state": "failed",
                "data": None,
                "error": message,
                "ran_at": _now(),
            }
    research = {**research, "local_competitors": result}
    await repo.update(audit_id, sections={"research": research})
    return to_wire(await fetch_audit(repo, audit_id))
