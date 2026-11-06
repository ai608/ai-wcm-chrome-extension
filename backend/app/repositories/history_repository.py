from datetime import datetime
from typing import Any

import asyncpg


class HistoryBriefRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def find(
        self, contact_id: str, input_hash: str, prompt_version: int
    ) -> dict[str, Any] | None:
        """The brief made from exactly these facts, if there is one."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT text, created_at FROM extension.history_briefs "
                "WHERE ghl_contact_id = $1 AND input_hash = $2 AND prompt_version = $3",
                contact_id,
                input_hash,
                prompt_version,
            )
        return dict(row) if row else None

    async def latest(self, contact_id: str) -> dict[str, Any] | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT text, created_at FROM extension.history_briefs "
                "WHERE ghl_contact_id = $1 ORDER BY created_at DESC LIMIT 1",
                contact_id,
            )
        return dict(row) if row else None

    async def save(
        self,
        contact_id: str,
        input_hash: str,
        prompt_version: int,
        model: str,
        text: str,
        requested_by: str,
        cost_micro: int,
        tokens: int,
    ) -> datetime | None:
        """Insert once. None when another request saved the same facts first."""
        async with self._pool.acquire() as conn:
            created: datetime | None = await conn.fetchval(
                "INSERT INTO extension.history_briefs "
                "(ghl_contact_id, input_hash, prompt_version, model, text, requested_by, "
                " cost_micro, tokens) VALUES ($1, $2, $3, $4, $5, $6::uuid, $7, $8) "
                "ON CONFLICT (ghl_contact_id, input_hash, prompt_version) DO NOTHING "
                "RETURNING created_at",
                contact_id,
                input_hash,
                prompt_version,
                model,
                text,
                requested_by,
                cost_micro,
                tokens,
            )
        return created
