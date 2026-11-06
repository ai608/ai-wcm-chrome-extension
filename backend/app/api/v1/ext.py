import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.core.config import settings
from app.core.dependencies import get_http_client, require_extension_access
from app.core.exceptions import AppError
from app.models.user import UserProfile
from app.repositories.audit_repository import AuditRepository
from app.services import apollo, ghl, openrouter_usage, site_audit

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_extension_access)], tags=["ext"])

_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


def _load_script() -> dict[str, Any]:
    # Only v<N>.json goes live; v<N>.draft.json from the analysis CLI must not match.
    files = [p for p in _SCRIPTS.iterdir() if re.fullmatch(r"v\d+\.json", p.name)]
    if not files:
        raise RuntimeError(f"No script definition in {_SCRIPTS}")
    script: dict[str, Any] = json.loads(
        max(files, key=lambda p: int(p.stem[1:])).read_text()
    )
    return script


def _field_keys(node: Any) -> set[str]:
    if isinstance(node, dict):
        keys = {node["fieldKey"]} if "fieldKey" in node else set()
        return keys.union(*(_field_keys(v) for v in node.values()))
    if isinstance(node, list):
        return set().union(*(_field_keys(v) for v in node))
    return set()


SCRIPT = _load_script()
SCRIPT_KEYS = _field_keys(SCRIPT)

Http = httpx.AsyncClient


@router.get("/config")
async def get_config() -> dict[str, Any]:
    return {
        "ghl_location_id": settings.GHL_SALES_LOCATION_ID,
        "booking_widget_url": settings.GHL_BOOKING_WIDGET_URL,
        "script_version": SCRIPT["version"],
    }


def _usd(micro: int) -> float:
    return round(micro / 1_000_000, 4)


@router.get("/admin/ai-usage")
async def ai_usage(
    request: Request,
    refresh: bool = False,
    profile: UserProfile = Depends(require_extension_access),
    http: Http = Depends(get_http_client),
) -> dict[str, Any]:
    """AI spend of all users, for the Settings screen. Owners and admins only."""
    if profile.role not in ("owner", "admin"):
        raise AppError(403, "forbidden", "Only an owner or admin can see AI usage")
    from app.api.v1 import research  # late: research imports this module's siblings

    repo = research._repo(request)
    live = await openrouter_usage.fetch(http, force=refresh)
    tracked = await repo.ai_spend_summary()
    return {
        **live,
        "tracked": {
            "total_usd": _usd(tracked["total"]),
            "today_usd": _usd(tracked["day"]),
            "week_usd": _usd(tracked["week"]),
            "month_usd": _usd(tracked["month"]),
            "audits_usd": _usd(tracked["audits"]),
            "ai_visibility_usd": _usd(tracked["ai_visibility"]),
            "users": tracked["users"],
        },
        "fetched_at": datetime.now(UTC).isoformat(),
    }


@router.get("/script")
async def get_script() -> dict[str, Any]:
    return SCRIPT


def _by_key(catalog: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {f["fieldKey"]: f for f in catalog if f.get("fieldKey") in SCRIPT_KEYS}


def _values(
    contact: dict[str, Any], by_key: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    raw = {f["id"]: f.get("value") for f in contact.get("customFields", [])}
    return {k: raw.get(f["id"]) for k, f in by_key.items()}


def _wire_contact(c: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": c["id"],
        "first_name": c.get("firstName") or "",
        "last_name": c.get("lastName") or "",
        "company_name": c.get("companyName") or "",
        "email": c.get("email") or "",
        "phone": c.get("phone") or "",
        "city": c.get("city") or "",
        "state": c.get("state") or "",
        "postal_code": c.get("postalCode") or "",
        "website": c.get("website") or "",
        "tags": c.get("tags") or [],
    }


async def _research_values(
    request: Request, http: Http, contact: dict[str, Any]
) -> dict[str, Any]:
    """Script fields the latest research audit can fill: Google rating and review count (when the
    audit matched a GBP) and the Apollo revenue estimate."""
    pool = getattr(request.app.state, "pool", None)
    website = await ghl.contact_website(http, contact)
    if pool is None or not website:
        return {}
    _, host = site_audit.normalize_url(website)
    row = await AuditRepository(pool).latest(
        host.lower().rstrip(".").removeprefix("www.")
    )
    business = (row["business"] if row else None) or {}
    if isinstance(business, str):
        business = json.loads(business)
    values: dict[str, Any] = {}
    gbp = business.get("gbp") or {}
    if gbp.get("matched"):
        values["contact.google_rating"] = gbp.get("rating")
        values["contact.google_review_count"] = gbp.get("review_count")
    company = business.get("company") or {}
    # Audits saved before Apollo's number was stored only have the printed text ("500K").
    revenue = company.get("annual_revenue") or apollo.money(
        company.get("estimated_revenue")
    )
    if revenue:
        values["contact.annual_revenue_"] = revenue
    return values


def _site_origin(value: Any) -> str | None:
    """The site's root ("https://clinic.com") from the contact's Website value. GHL often holds
    a page or junk path ("https://clinic.com/.wf_auth"); the script wants the site itself."""
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    parts = urlsplit(value if "://" in value else f"https://{value}")
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    return f"{parts.scheme}://{parts.hostname.lower()}"


@router.get("/contacts/{contact_id}/context")
async def get_context(
    contact_id: str, request: Request, http: Http = Depends(get_http_client)
) -> dict[str, Any]:
    contact = await ghl.get_contact(http, contact_id)
    catalog = await ghl.get_catalog(http)
    by_key = _by_key(catalog)
    values = _values(contact, by_key)
    # GHL wins. Only a field empty in GHL takes the research number (or the contact's own Website),
    # and is saved back to GHL.
    own = {"contact.your_website_url": _site_origin(contact.get("website"))}
    fill = {
        k: v
        for k, v in {**(await _research_values(request, http, contact)), **own}.items()
        if k in by_key and values.get(k) in (None, "", []) and v is not None
    }
    saved: list[str] = []
    if fill:
        try:
            writes = [
                {"id": by_key[k]["id"], "field_value": v} for k, v in fill.items()
            ]
            if (
                "contact.annual_revenue_" in fill
            ):  # keep the range field in step, as typing does
                writes += _range_write(catalog, fill["contact.annual_revenue_"])
            await ghl.update_custom_fields(http, contact_id, writes)
            saved = list(fill)
        except AppError:
            logger.warning("Could not save research values to GHL for %s", contact_id)
        values.update(fill)
    return {
        "auto_saved": saved,
        "contact": _wire_contact(contact),
        "field_values": values,
        # ponytail: O1 enrichment lookup not wired, always not_enriched
        "enrichment": {
            "status": "not_enriched",
            "services": [],
            "google_rating": None,
            "google_review_count": None,
            "score": None,
            "updated_at": None,
        },
    }


@router.get("/contacts/{contact_id}/script")
async def get_personalized_script(contact_id: str) -> dict[str, Any]:
    # ponytail: AI personalization not built; static script only
    return {
        "status": "none",
        "script_version": SCRIPT["version"],
        "generated_at": None,
        "slots": {},
        "error": None,
    }


def _coerce(field: dict[str, Any], key: str, value: Any) -> Any:
    kind = field.get("dataType")
    bad = AppError(422, "validation_error", f"Invalid value for {key}")
    if value is None or value == "" or value == []:
        return [] if kind in ("MULTIPLE_OPTIONS", "CHECKBOX") else ""
    options = field.get("picklistOptions") or []
    if kind in ("NUMERICAL", "MONETORY"):
        try:
            n = float(value)
        except (TypeError, ValueError):
            raise bad from None
        return int(n) if n.is_integer() else n
    if kind in ("MULTIPLE_OPTIONS", "CHECKBOX"):
        vals = value if isinstance(value, list) else [value]
        if not all(isinstance(v, str) for v in vals) or (
            options and not set(vals) <= set(options)
        ):
            raise bad
        return vals
    if isinstance(value, (list, dict)):
        raise bad
    if kind in ("SINGLE_OPTIONS", "RADIO") and options and value not in options:
        raise bad
    return str(value)


# Upper bounds of the first three "Annual Revenue (selection)" options, in GHL order:
# Under $450k, $450k-$1M, $1M-$1.5M, then $1.5M +. A bound belongs to the higher range.
REVENUE_BOUNDS = (450_000, 1_000_000, 1_500_000)


def _revenue_range(options: list[str], amount: Any) -> str | None:
    if len(options) != len(REVENUE_BOUNDS) + 1 or not isinstance(amount, int | float):
        return None  # options were edited in GHL; don't guess
    return options[sum(amount >= b for b in REVENUE_BOUNDS)]


def _range_write(catalog: list[dict[str, Any]], amount: Any) -> list[dict[str, Any]]:
    """The GHL write that sets the "Annual Revenue (selection)" range for a dollar amount."""
    rng = next(
        (f for f in catalog if f.get("fieldKey") == "contact.annual_revenue"), None
    )
    bucket = _revenue_range(rng.get("picklistOptions") or [], amount) if rng else None
    return [{"id": rng["id"], "field_value": bucket}] if rng and bucket else []


class PatchFields(BaseModel):
    fields: dict[str, Any]


@router.patch("/contacts/{contact_id}/fields")
async def patch_fields(
    contact_id: str, body: PatchFields, http: Http = Depends(get_http_client)
) -> dict[str, Any]:
    unknown = body.fields.keys() - SCRIPT_KEYS
    if unknown:
        raise AppError(422, "validation_error", f"Unknown field {min(unknown)}")
    await ghl.get_contact(http, contact_id)  # location guard
    by_key = _by_key(await ghl.get_catalog(http))
    missing = body.fields.keys() - by_key.keys()
    if missing:
        raise AppError(422, "validation_error", f"No GHL field for {min(missing)}")
    values = {k: _coerce(by_key[k], k, v) for k, v in body.fields.items()}
    writes = [{"id": by_key[k]["id"], "field_value": v} for k, v in values.items()]
    # Typing the dollar amount also sets the matching range field in GHL.
    amount = values.get("contact.annual_revenue_")
    if amount not in (None, ""):
        writes += _range_write(await ghl.get_catalog(http), amount)
    await ghl.update_custom_fields(http, contact_id, writes)
    return {
        "field_values": {k: (v if v != "" else None) for k, v in values.items()},
        "updated_at": datetime.now(UTC).isoformat(),
    }
