import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

import asyncpg

REFRESH_GRACE = timedelta(
    seconds=60
)  # how long a just-replaced refresh token still works


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_tokens() -> tuple[str, str, datetime, datetime]:
    now = datetime.now(UTC)
    return (
        "wcm_at_" + secrets.token_urlsafe(32),
        "wcm_rt_" + secrets.token_urlsafe(32),
        now + timedelta(minutes=15),
        now + timedelta(days=30),
    )


class AuthSessionRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(self, user_id: str, handoff_jti: str) -> tuple[str, str, datetime]:
        access, refresh, access_expires, refresh_expires = new_tokens()
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO extension.auth_sessions "
                "(user_id, handoff_jti_hash, access_hash, refresh_hash, "
                "access_expires_at, refresh_expires_at) "
                "VALUES ($1, $2, $3, $4, $5, $6)",
                UUID(user_id),
                token_hash(handoff_jti),
                token_hash(access),
                token_hash(refresh),
                access_expires,
                refresh_expires,
            )
        return access, refresh, access_expires

    async def user_id_for_access(self, access: str) -> str | None:
        async with self._pool.acquire() as conn:
            value = await conn.fetchval(
                "SELECT user_id FROM extension.auth_sessions "
                "WHERE access_hash = $1 AND access_expires_at > now() "
                "AND refresh_expires_at > now() AND revoked_at IS NULL",
                token_hash(access),
            )
        return str(value) if value is not None else None

    async def rotate(self, refresh: str) -> tuple[str, str, str, datetime] | None:
        """Swap a refresh token for a new pair. The token just replaced still works for
        REFRESH_GRACE_S more seconds (and only for as long as the first replacement), so a
        client whose answer was lost can ask again instead of being signed out."""
        presented = token_hash(refresh)
        async with self._pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                "SELECT id, user_id, refresh_hash, prev_refresh_until "
                "FROM extension.auth_sessions "
                "WHERE (refresh_hash = $1 OR prev_refresh_hash = $1) "
                "AND refresh_expires_at > now() AND revoked_at IS NULL FOR UPDATE",
                presented,
            )
            if row is None:
                return None
            now = datetime.now(UTC)
            replay = (
                presented != row["refresh_hash"]
            )  # the token that was just replaced
            if replay and (
                row["prev_refresh_until"] is None or row["prev_refresh_until"] <= now
            ):
                return None  # replaced a while ago: a stolen or stale token, not a lost answer
            # A replay keeps its original window: it cannot be extended by asking again.
            until = row["prev_refresh_until"] if replay else now + REFRESH_GRACE
            access, next_refresh, access_expires, refresh_expires = new_tokens()
            await conn.execute(
                "UPDATE extension.auth_sessions SET access_hash = $1, "
                "refresh_hash = $2, access_expires_at = $3, refresh_expires_at = $4, "
                "prev_refresh_hash = $5, prev_refresh_until = $6 WHERE id = $7",
                token_hash(access),
                token_hash(next_refresh),
                access_expires,
                refresh_expires,
                presented,
                until,
                row["id"],
            )
            return str(row["user_id"]), access, next_refresh, access_expires

    async def revoke_access(self, access: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE extension.auth_sessions SET revoked_at = now() "
                "WHERE access_hash = $1 AND revoked_at IS NULL",
                token_hash(access),
            )

    async def revoke_user(self, user_id: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE extension.auth_sessions SET revoked_at = now() "
                "WHERE user_id = $1 AND revoked_at IS NULL",
                UUID(user_id),
            )
