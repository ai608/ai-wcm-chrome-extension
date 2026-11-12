"""The sales report header: who it is for, who made it, and a one-paragraph summary."""

from datetime import UTC, datetime
from typing import Any

from app.models.user import UserProfile


def build(audit: dict[str, Any], profile: UserProfile) -> dict[str, Any]:
    nap = (audit.get("business") or {}).get("nap") or {}
    overview = audit.get("overview") or {}
    prepared_for = nap.get("name") or audit["domain"]
    intro = f"This report reviews {audit['domain']} the way a prospective patient and Google see it."
    if overview.get("score") is not None:
        intro += (
            f" It scores {overview['score']}/100 ({overview.get('grade')}),"
            f" with {overview.get('issue_count', 0)} items to fix."
        )
    return {
        "audit": audit,
        "prepared_for": prepared_for,
        "prepared_by": f"WCM · {profile.full_name or profile.email}",
        "generated_at": datetime.now(UTC).isoformat(),
        "intro": intro,
    }
