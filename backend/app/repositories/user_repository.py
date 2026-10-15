# Copied from AI Lead Pipeline backend app/repositories/user_repository.py, trimmed for the Sales Assistant.
import asyncpg

from app.core.encryption import decrypt_value
from app.models.user import UserProfile

_PROFILE_COLUMNS = (
    "id, email, full_name, avatar_url, role, is_active, admin_id, pending_admin_id, "
    "pending_role, invited_by_id, totp_enabled, (totp_secret IS NOT NULL) AS totp_configured, "
    "last_login_at, automation_access, created_at, updated_at"
)


class UserRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get_by_id(self, user_id: str) -> UserProfile | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_PROFILE_COLUMNS} FROM public.profiles WHERE id = $1",
                user_id,
            )
        return UserProfile.from_row(dict(row)) if row is not None else None

    async def get_totp_secret(self, user_id: str) -> str | None:
        async with self._pool.acquire() as conn:
            value = await conn.fetchval(
                "SELECT totp_secret FROM public.profiles WHERE id = $1", user_id
            )
        return decrypt_value(value) if value else None
