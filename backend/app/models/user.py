# Copied from AI Lead Pipeline backend app/models/user.py, trimmed for the Sales Assistant.
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.config import settings


def _full_access_emails() -> set[str]:
    return {
        e.strip().lower() for e in settings.FULL_ACCESS_EMAILS.split(",") if e.strip()
    }


def _parse_dt(value: Any) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(value)


def _parse_dt_opt(value: Any) -> datetime | None:
    if value is None:
        return None
    return _parse_dt(value)


def _parse_automation_access(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except ValueError:
            return {}
        value = parsed if isinstance(parsed, dict) else {}
    if not isinstance(value, dict):
        return {}

    fixed: dict[str, Any] = {}
    for key, grant in value.items():
        if isinstance(grant, str):
            try:
                grant = json.loads(grant)
            except ValueError:
                continue
        if isinstance(grant, dict):
            fixed[str(key)] = grant
    return fixed


@dataclass
class UserProfile:
    id: str
    email: str
    full_name: str | None
    avatar_url: str | None
    role: str
    is_active: bool
    admin_id: str | None
    created_at: datetime
    updated_at: datetime
    pending_admin_id: str | None = None
    pending_role: str | None = None
    invited_by_id: str | None = None
    totp_enabled: bool = False
    totp_configured: bool = False
    last_login_at: datetime | None = None
    automation_access: dict[str, Any] | None = None

    @property
    def is_owner(self) -> bool:
        return self.role == "owner"

    @property
    def is_platform_super_admin(self) -> bool:
        return self.email.strip().lower() in _full_access_emails()

    @property
    def has_full_access(self) -> bool:
        return self.is_owner or self.is_platform_super_admin

    @property
    def automation_access_map(self) -> dict[str, Any]:
        return (
            self.automation_access if isinstance(self.automation_access, dict) else {}
        )

    def _grant_role(self, automation_id: str) -> str | None:
        grant = self.automation_access_map.get(automation_id)
        if not isinstance(grant, dict):
            return None
        role = grant.get("role")
        return role if role in ("admin", "user") else None

    def can_open(self, automation_id: str) -> bool:
        if self.has_full_access:
            return True
        if automation_id in self.automation_access_map:
            return self._grant_role(automation_id) is not None
        return self.role in ("owner", "admin")

    @staticmethod
    def from_row(row: dict[str, Any]) -> "UserProfile":
        return UserProfile(
            id=str(row["id"]),
            email=row["email"],
            full_name=row.get("full_name"),
            avatar_url=row.get("avatar_url"),
            role=row.get("role", "user"),
            is_active=row.get("is_active", True),
            admin_id=str(row["admin_id"]) if row.get("admin_id") else None,
            pending_admin_id=str(row["pending_admin_id"])
            if row.get("pending_admin_id")
            else None,
            pending_role=row.get("pending_role"),
            invited_by_id=str(row["invited_by_id"])
            if row.get("invited_by_id")
            else None,
            totp_enabled=row.get("totp_enabled", False),
            totp_configured=(
                bool(row["totp_configured"])
                if "totp_configured" in row
                else row.get("totp_secret") is not None
            ),
            last_login_at=_parse_dt_opt(row.get("last_login_at")),
            automation_access=_parse_automation_access(row.get("automation_access")),
            created_at=_parse_dt(row["created_at"]),
            updated_at=_parse_dt(row["updated_at"]),
        )
