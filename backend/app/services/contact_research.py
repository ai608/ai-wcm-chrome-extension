"""Research for a CRM contact: find the contact's website, then show or start its audit.
The repository is taken late (`repo_for`), after the contact checks, as before."""

from collections.abc import Callable
from typing import Any

import httpx

from app.repositories.audit_repository import AuditRepository, to_wire
from app.services import audit_runner, ghl, site_audit


async def _site(
    http: httpx.AsyncClient, contact_id: str
) -> tuple[dict[str, Any], str | None]:
    contact = await ghl.get_contact(http, contact_id)  # location guard
    return contact, await ghl.contact_website(http, contact)


async def latest(
    repo_for: Callable[[], AuditRepository], http: httpx.AsyncClient, contact_id: str
) -> dict[str, Any]:
    _, website = await _site(http, contact_id)
    if not website:
        return {"audit": None, "reason": "no_website"}
    _, host = site_audit.normalize_url(website)
    row = await repo_for().latest(audit_runner.domain_of(host))
    return {"audit": to_wire(row) if row else None}


async def start(
    repo_for: Callable[[], AuditRepository],
    http: httpx.AsyncClient,
    user_id: str,
    contact_id: str,
    force: bool,
) -> dict[str, Any]:
    contact, website = await _site(http, contact_id)
    if not website:
        return {"audit": None, "reason": "no_website"}
    hints = (
        {"name": contact.get("companyName") or ""} if contact.get("companyName") else {}
    )
    row, _ = await audit_runner.start(repo_for(), http, user_id, website, force, hints)
    return {"audit": to_wire(row)}
