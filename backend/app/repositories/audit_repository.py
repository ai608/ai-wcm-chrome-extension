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
# Latest AI visibility run, already in wire shape. Read through a join so progress writes touch
# only the small run row, never the large audit JSON columns.
_AI_RUN = (
    "(SELECT jsonb_build_object('state', r.status, 'data', r.data, 'error', r.error, "
    "'ran_at', COALESCE(r.finished_at, r.created_at)) "
    "FROM extension.ai_visibility_runs r WHERE r.audit_id = audits.id "
    "ORDER BY r.created_at DESC LIMIT 1) AS ai_run"
)
_COLS = (
    "id, url, domain, status, error, section_state, created_at, finished_at, trace, "
    + ", ".join(COLUMNS.values())
    + ", "
    + _AI_RUN
)


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def to_wire(row: asyncpg.Record) -> dict[str, Any]:
    research = _json(row["research"])
    ai_run = _json(row.get("ai_run"))
    if research and ai_run:
        research = {**research, "ai_visibility": ai_run}
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

    async def set_audit_spend(
        self, audit_id: str, cost_micro: int, tokens: int
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE extension.audits SET ai_cost_micro = $2, ai_tokens = $3 "
                "WHERE id = $1",
                UUID(audit_id),
                cost_micro,
                tokens,
            )

    async def ai_spend_summary(self) -> dict[str, Any]:
        """What the app has spent on AI, all users: audits and AI visibility runs, in micro-USD,
        over the last day, week, month and all time. Spend before this was tracked is not in it."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "WITH s AS ("
                " SELECT 'audits' AS src, requested_by, created_at, ai_cost_micro AS c "
                " FROM extension.audits WHERE ai_cost_micro > 0 "
                " UNION ALL "
                " SELECT 'ai_visibility', requested_by, created_at, cost_micro "
                " FROM extension.ai_visibility_runs WHERE cost_micro > 0 "
                " UNION ALL "
                " SELECT 'history_briefs', requested_by, created_at, cost_micro "
                " FROM extension.history_briefs WHERE cost_micro > 0) "
                "SELECT src, COALESCE(SUM(c), 0)::bigint AS total, "
                " COALESCE(SUM(c) FILTER (WHERE created_at >= now() - interval '1 day'), 0)::bigint AS day, "
                " COALESCE(SUM(c) FILTER (WHERE created_at >= now() - interval '7 days'), 0)::bigint AS week, "
                " COALESCE(SUM(c) FILTER (WHERE created_at >= now() - interval '30 days'), 0)::bigint AS month "
                "FROM s GROUP BY src"
            )
            users = await conn.fetchval(
                "SELECT count(DISTINCT requested_by) FROM ("
                " SELECT requested_by FROM extension.audits WHERE ai_cost_micro > 0 "
                " UNION SELECT requested_by FROM extension.ai_visibility_runs WHERE cost_micro > 0"
                " UNION SELECT requested_by FROM extension.history_briefs WHERE cost_micro > 0) u"
            )
        by = {r["src"]: int(r["total"]) for r in rows}
        return {
            "total": sum(int(r["total"]) for r in rows),
            "day": sum(int(r["day"]) for r in rows),
            "week": sum(int(r["week"]) for r in rows),
            "month": sum(int(r["month"]) for r in rows),
            "audits": by.get("audits", 0),
            "ai_visibility": by.get("ai_visibility", 0),
            "history_briefs": by.get("history_briefs", 0),
            "users": int(users or 0),
        }

    async def create_ai_run(
        self,
        audit_id: str,
        user_id: str,
        kind: str = "lite",
        config: dict[str, Any] | None = None,
    ) -> str | None:
        """Start a run. None when this audit already has one running (unique index)."""
        async with self._pool.acquire() as conn:
            try:
                row = await conn.fetchrow(
                    "INSERT INTO extension.ai_visibility_runs "
                    "(audit_id, requested_by, status, kind, config, data) "
                    "VALUES ($1, $2, 'running', $3, $4::jsonb, $5::jsonb) RETURNING id",
                    UUID(audit_id),
                    UUID(user_id),
                    kind,
                    json.dumps(config) if config is not None else None,
                    # So the panel knows at once that this is a full report, before the job's
                    # first progress write.
                    json.dumps(
                        {
                            "version": 1,
                            "kind": "full",
                            "prompts": [],
                            "engines": [],
                            "log": [],
                        }
                    )
                    if kind == "full"
                    else None,
                )
            except asyncpg.UniqueViolationError:
                return None
            return str(row["id"]) if row else None

    async def save_ai_run(
        self,
        run_id: str,
        *,
        status: str | None = None,
        data: dict[str, Any] | None = None,
        error: str | None = None,
        cost_micro: int | None = None,
        tokens: int | None = None,
        finished: bool = False,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE extension.ai_visibility_runs SET "
                "status = COALESCE($2, status), "
                "data = COALESCE($3::jsonb, data), "
                "error = COALESCE($4, error), "
                "cost_micro = COALESCE($5, cost_micro), "
                "tokens = COALESCE($6, tokens), "
                "finished_at = CASE WHEN $7 THEN now() ELSE finished_at END "
                "WHERE id = $1",
                UUID(run_id),
                status,
                json.dumps(data) if data is not None else None,
                error,
                cost_micro,
                tokens,
                finished,
            )

    async def ai_spend_micro(self, user_id: str) -> int:
        """What this user's runs cost in the last 24 hours (micro-USD)."""
        async with self._pool.acquire() as conn:
            total = await conn.fetchval(
                "SELECT COALESCE(SUM(cost_micro), 0) FROM extension.ai_visibility_runs "
                "WHERE requested_by = $1 AND created_at > now() - interval '1 day'",
                UUID(user_id),
            )
            return int(total or 0)

    async def fail_interrupted(self) -> int:
        """Single-instance sweeper: anything still queued/running at startup was interrupted."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE extension.ai_visibility_runs SET status = 'failed', "
                "error = 'interrupted', finished_at = now() "
                "WHERE status = 'running' AND kind = 'lite'"  # full runs resume instead
            )
            res: str = await conn.execute(
                "UPDATE extension.audits SET status = 'failed', error = 'interrupted', "
                "finished_at = now() WHERE status IN ('queued', 'running')"
            )
            return int(res.split()[-1])

    # ── full AI visibility report ─────────────────────────────────────────────────────────

    async def get_ai_run(self, run_id: str) -> dict[str, Any] | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, audit_id, requested_by, status, kind, config, created_at "
                "FROM extension.ai_visibility_runs WHERE id = $1",
                UUID(run_id),
            )
        if row is None:
            return None
        return {
            "id": str(row["id"]),
            "audit_id": str(row["audit_id"]),
            "requested_by": str(row["requested_by"]),
            "status": row["status"],
            "kind": row["kind"],
            "config": _json(row["config"]) or {},
            "created_at": row["created_at"],
        }

    async def patch_ai_config(self, run_id: str, patch: dict[str, Any]) -> None:
        """Merge keys into the run's frozen config (prompts, competitors, overhead spend...)."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE extension.ai_visibility_runs "
                "SET config = COALESCE(config, '{}'::jsonb) || $2::jsonb WHERE id = $1",
                UUID(run_id),
                json.dumps(patch),
            )

    async def running_full_runs(self) -> list[str]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id FROM extension.ai_visibility_runs "
                "WHERE status = 'running' AND kind = 'full' ORDER BY created_at"
            )
        return [str(r["id"]) for r in rows]

    async def save_ai_answer(
        self,
        run_id: str,
        prompt_idx: int,
        engine: str,
        run_no: int,
        *,
        text: str | None = None,
        urls: list[str] | None = None,
        error: str | None = None,
        tokens: int = 0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost_micro: int = 0,
    ) -> None:
        """One paid answer, saved the moment it arrives. A second write for the same cell is
        ignored when the first is a good answer, so a restart can never overwrite (or pay for)
        one it already has. A failed answer is replaced, so it can be asked again."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO extension.ai_visibility_answers (run_id, prompt_idx, engine, run_no, "
                "status, text, urls, error, tokens, prompt_tokens, completion_tokens, cost_micro) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10, $11, $12) "
                # A good answer is never overwritten (a restart cannot pay twice). A failed one is
                # replaced, so asking it again can fix it.
                "ON CONFLICT (run_id, prompt_idx, engine, run_no) DO UPDATE SET "
                "status = EXCLUDED.status, text = EXCLUDED.text, urls = EXCLUDED.urls, "
                "error = EXCLUDED.error, tokens = EXCLUDED.tokens, "
                "prompt_tokens = EXCLUDED.prompt_tokens, "
                "completion_tokens = EXCLUDED.completion_tokens, "
                "cost_micro = EXCLUDED.cost_micro, facts = NULL "
                "WHERE extension.ai_visibility_answers.status = 'failed'",
                UUID(run_id),
                prompt_idx,
                engine,
                run_no,
                "failed" if error else "ok",
                text,
                json.dumps(urls) if urls is not None else None,
                error,
                tokens,
                prompt_tokens,
                completion_tokens,
                cost_micro,
            )

    async def save_ai_facts(
        self,
        run_id: str,
        prompt_idx: int,
        engine: str,
        run_no: int,
        facts: dict[str, Any],
        judge_tokens: int = 0,
        judge_cost_micro: int = 0,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE extension.ai_visibility_answers SET facts = $5::jsonb, "
                "judge_tokens = $6, judge_cost_micro = $7 "
                "WHERE run_id = $1 AND prompt_idx = $2 AND engine = $3 AND run_no = $4",
                UUID(run_id),
                prompt_idx,
                engine,
                run_no,
                json.dumps(facts),
                judge_tokens,
                judge_cost_micro,
            )

    async def ai_answer_keys(self, run_id: str) -> set[tuple[int, str, int]]:
        """Cells that already have an answer row (ok or failed): never asked twice."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT prompt_idx, engine, run_no FROM extension.ai_visibility_answers "
                "WHERE run_id = $1",
                UUID(run_id),
            )
        return {(int(r["prompt_idx"]), r["engine"], int(r["run_no"])) for r in rows}

    async def ai_answers_to_read(self, run_id: str) -> list[dict[str, Any]]:
        """Good answers the judge has not read yet: no facts, or a read that failed earlier (it is
        tried again after a restart)."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT prompt_idx, engine, run_no, text, urls FROM extension.ai_visibility_answers "
                "WHERE run_id = $1 AND status = 'ok' AND (facts IS NULL OR facts->>'judge_failed' = 'true') "
                "ORDER BY prompt_idx, engine, run_no",
                UUID(run_id),
            )
        return [
            {
                "prompt_idx": int(r["prompt_idx"]),
                "engine": r["engine"],
                "run_no": int(r["run_no"]),
                "text": r["text"] or "",
                "urls": _json(r["urls"]) or [],
            }
            for r in rows
        ]

    async def ai_answers_for_log(self, run_id: str) -> list[dict[str, Any]]:
        """Saved answers with their text and what they cost, to rebuild the step log and the
        spend after a restart."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT prompt_idx, engine, run_no, status, error, tokens, cost_micro, text, urls, "
                "judge_tokens, judge_cost_micro "
                "FROM extension.ai_visibility_answers WHERE run_id = $1 "
                "ORDER BY prompt_idx, engine, run_no",
                UUID(run_id),
            )
        return [
            {**dict(r), "text": r["text"] or "", "urls": _json(r["urls"]) or []}
            for r in rows
        ]

    async def ai_answer_texts(
        self, run_id: str, *, limit: int = 20_000
    ) -> list[dict[str, Any]]:
        """Good answers' text for the one batched competitor-discovery step."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT prompt_idx, engine, run_no, left(text, $2) AS text "
                "FROM extension.ai_visibility_answers WHERE run_id = $1 AND status = 'ok' "
                "ORDER BY prompt_idx, engine, run_no",
                UUID(run_id),
                limit,
            )
        return [dict(r) for r in rows]

    async def ai_answer_summary(self, run_id: str) -> list[dict[str, Any]]:
        """Everything scoring needs (no text): one row per answer cell."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT prompt_idx, engine, run_no, status, error, facts, tokens, prompt_tokens, "
                "completion_tokens, cost_micro, judge_tokens, judge_cost_micro "
                "FROM extension.ai_visibility_answers WHERE run_id = $1 "
                "ORDER BY prompt_idx, engine, run_no",
                UUID(run_id),
            )
        return [{**dict(r), "facts": _json(r["facts"])} for r in rows]

    async def ai_answer_page(
        self,
        run_id: str,
        *,
        engine: str | None,
        prompt_idx: int | None,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT prompt_idx, engine, run_no, status, text, urls, error, facts, tokens, "
                "cost_micro FROM extension.ai_visibility_answers WHERE run_id = $1 "
                "AND ($2::text IS NULL OR engine = $2) "
                "AND ($3::int IS NULL OR prompt_idx = $3) "
                "ORDER BY prompt_idx, engine, run_no LIMIT $4 OFFSET $5",
                UUID(run_id),
                engine,
                prompt_idx,
                limit,
                offset,
            )
        return [
            {**dict(r), "urls": _json(r["urls"]) or [], "facts": _json(r["facts"])}
            for r in rows
        ]
