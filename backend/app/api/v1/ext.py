import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.config import settings
from app.core.dependencies import get_http_client, require_extension_access
from app.core.exceptions import AppError
from app.services import ghl

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


@router.get("/contacts/{contact_id}/context")
async def get_context(
    contact_id: str, http: Http = Depends(get_http_client)
) -> dict[str, Any]:
    contact = await ghl.get_contact(http, contact_id)
    by_key = _by_key(await ghl.get_catalog(http))
    return {
        "contact": _wire_contact(contact),
        "field_values": _values(contact, by_key),
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
    await ghl.update_custom_fields(
        http,
        contact_id,
        [{"id": by_key[k]["id"], "field_value": v} for k, v in values.items()],
    )
    return {
        "field_values": {k: (v if v != "" else None) for k, v in values.items()},
        "updated_at": datetime.now(UTC).isoformat(),
    }
