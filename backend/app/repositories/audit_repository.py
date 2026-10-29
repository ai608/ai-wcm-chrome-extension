import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import asyncpg

FRESH_FOR = timedelta(hours=24)
# Wire section key -> column in extension.audits (see migrations/..._init.sql).
COLUMNS = {
    "overview": "overview",
    "business": "business",
    "on_page": "on_page",
    "schema": "schema_data",
    "site": "site",
    "convert": "convert",
    "research": "research",
}
_COLS = (
    "id, url, domain, status, error, section_state, created_at, finished_at, trace, "
    + ", ".join(COLUMNS.values())
)


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def to_wire(row: asyncpg.Record) -> dict[str, Any]:
    research = _json(row["research"])
    return {
        "id": str(row["id"]),
        "url": row["url"],
        "domain": row["domain"],
        "status": row["status"],
        "error": row["error"],
        "created_at": row["created_at"].isoformat(),
        "finished_at": row["finished_at"].isoformat() if row["finished_at"] else None,
        "section_state": _json(row["section_state"]),
        "trace": _json(row["trace"]) or [],
        **{k: _json(row[col]) for k, col in COLUMNS.items() if k != "research"},
        "research": research or None,
    }


class AuditRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(
        self, user_id: str, url: str, domain: str, state: dict[str, str]
    ) -> asyncpg.Record:
        async with self._pool.acquire() as conn:
            row: asyncpg.Record = await conn.fetchrow(
                "INSERT INTO extension.audits "
                "(requested_by, url, domain, status, section_state) "
                f"VALUES ($1, $2, $3, 'queued', $4::jsonb) RETURNING {_COLS}",
                UUID(user_id),
                url,
                domain,
                json.dumps(state),
            )
            return row

    async def get(self, audit_id: str) -> asyncpg.Record | None:
        try:
            uid = UUID(audit_id)
        except ValueError:
            return None
        async with self._pool.acquire() as conn:
            row: asyncpg.Record | None = await conn.fetchrow(
                f"SELECT {_COLS} FROM extension.audits WHERE id = $1", uid
            )
            return row

    async def latest(
        self, domain: str, fresh_only: bool = False
    ) -> asyncpg.Record | None:
        since = (
            datetime.now(UTC) - FRESH_FOR
            if fresh_only
            else datetime.min.replace(tzinfo=UTC)
        )
        async with self._pool.acquire() as conn:
            row: asyncpg.Record | None = await conn.fetchrow(
                f"SELECT {_COLS} FROM extension.audits "
                "WHERE domain = $1 AND created_at >= $2 AND status <> 'failed' "
                "ORDER BY created_at DESC LIMIT 1",
                domain,
                since,
            )
            return row

    async def update(
        self,
        audit_id: str,
        *,
        status: str | None = None,
        error: str | None = None,
        state: dict[str, str] | None = None,
        sections: dict[str, Any] | None = None,
        finished: bool = False,
    ) -> None:
        sets = [
            "status = COALESCE($2, status)",
            "error = COALESCE($3, error)",
            "section_state = section_state || $4::jsonb",
            "finished_at = CASE WHEN $5 THEN now() ELSE finished_at END",
        ]
        args: list[Any] = [
            UUID(audit_id),
            status,
            error,
            json.dumps(state or {}),
            finished,
        ]
        for key, value in (sections or {}).items():
            col = COLUMNS[
                key
            ]  # KeyError on unknown keys; columns never come from input
            args.append(json.dumps(value))
            sets.append(f"{col} = ${len(args)}::jsonb")
        async with self._pool.acquire() as conn:
            await conn.execute(
                f"UPDATE extension.audits SET {', '.join(sets)} WHERE id = $1", *args
            )

    async def add_trace(self, audit_id: str, event: dict[str, Any]) -> None:
        # Append-only: one row per status change; the UI folds events by `id`, last one wins.
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE extension.audits SET trace = trace || $2::jsonb WHERE id = $1",
                UUID(audit_id),
                json.dumps([event]),
            )

    async def fail_interrupted(self) -> int:
        """Single-instance sweeper: anything still queued/running at startup was interrupted."""
        async with self._pool.acquire() as conn:
            res: str = await conn.execute(
                "UPDATE extension.audits SET status = 'failed', error = 'interrupted', "
                "finished_at = now() WHERE status IN ('queued', 'running')"
            )
            return int(res.split()[-1])
