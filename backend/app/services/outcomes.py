"""Save the outcome of a sales call: one note and one tag on the CRM contact, and a row of our
own. The save is safe to repeat: a retry after a lost answer finds what the first try did and
finishes it, so the contact never gets two notes for one call."""

from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.exceptions import AppError
from app.models.user import UserProfile
from app.repositories.outcome_repository import OutcomeRepository
from app.schemas.outcome import SaveOutcome
from app.services import ghl

TAG_PREFIX = (
    "call-outcome-"  # the CRM tag for outcome "has_agency" is "call-outcome-has-agency"
)


def outcomes_of(script: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The outcomes the call script offers, by id."""
    found: dict[str, dict[str, Any]] = {}
    for section in script.get("sections") or []:
        for block in section.get("blocks") or []:
            if block.get("type") == "outcome":
                found.update({o["id"]: o for o in block.get("outcomes") or []})
    return found


def tag_for(outcome_id: str) -> str:
    return TAG_PREFIX + outcome_id.replace("_", "-")


def note_text(
    outcome: dict[str, Any], note: str, profile: UserProfile, row_id: str
) -> str:
    """The CRM note. The marker at its end is how a retry recognises it was already made."""
    who = profile.full_name or profile.email
    lines = [f"Call outcome: {outcome['label']}"]
    if note.strip():
        lines.append(note.strip())
    lines.append(f"{who}, {datetime.now(UTC):%Y-%m-%d %H:%M} UTC {marker(row_id)}")
    return "\n".join(lines)


def marker(row_id: str) -> str:
    return f"[wcm-outcome:{row_id}]"


async def save(
    repo: OutcomeRepository,
    http: httpx.AsyncClient,
    script: dict[str, Any],
    profile: UserProfile,
    contact_id: str,
    body: SaveOutcome,
) -> dict[str, Any]:
    outcome = outcomes_of(script).get(body.outcome_id)
    if outcome is None:
        raise AppError(422, "unknown_outcome", "That outcome is not in the call script")
    if body.booked and not outcome.get("books"):
        raise AppError(
            422, "booked_not_allowed", "This outcome does not book an appointment"
        )
    await ghl.get_contact(http, contact_id)  # 404 unknown contact, 403 another location
    tag = tag_for(body.outcome_id)
    row_id, note_id = await repo.begin(
        contact_id=contact_id,
        user_id=profile.id,
        outcome_id=body.outcome_id,
        note=body.note.strip(),
        booked=body.booked,
        tag=tag,
        script_version=int(script["version"]),
    )
    if note_id:  # the same save was finished a moment ago: say so, change nothing
        return {"note_id": note_id, "tag": tag, "already_saved": True}
    # An earlier try may have made the note and lost its answer: look before making another.
    note_id = await ghl.find_note(http, contact_id, marker(row_id))
    if note_id is None:
        note_id = await ghl.add_note(
            http, contact_id, note_text(outcome, body.note, profile, row_id)
        )
    await ghl.add_tags(http, contact_id, [tag])
    await repo.finish(row_id, note_id)
    return {"note_id": note_id, "tag": tag, "already_saved": False}
