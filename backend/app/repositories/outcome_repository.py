import asyncpg

# A save repeated within this long is the same save (a retry), not a new call.
SAME_SAVE = "10 minutes"


class OutcomeRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def begin(
        self,
        *,
        contact_id: str,
        user_id: str,
        outcome_id: str,
        note: str,
        booked: bool,
        tag: str,
        script_version: int,
    ) -> tuple[str, str | None]:
        """(row id, CRM note id or None). A save made a moment ago returns its own row: with a
        note id when the CRM has it, without one when the earlier try stopped half way. Two
        requests for the same save at the same time are made one by a lock on its key."""
        key = f"{contact_id}|{user_id}|{outcome_id}|{note}"
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", key
            )
            row = await conn.fetchrow(
                "SELECT id, ghl_note_id FROM extension.call_outcomes "
                "WHERE ghl_contact_id = $1 AND user_id = $2::uuid AND outcome_id = $3 "
                "AND note = $4 AND created_at > now() - $5::interval "
                "ORDER BY created_at DESC LIMIT 1",
                contact_id,
                user_id,
                outcome_id,
                note,
                SAME_SAVE,
            )
            if row is None:
                row = await conn.fetchrow(
                    "INSERT INTO extension.call_outcomes (ghl_contact_id, user_id, "
                    "outcome_id, booked, note, tag, script_version) "
                    "VALUES ($1, $2::uuid, $3, $4, $5, $6, $7) RETURNING id, ghl_note_id",
                    contact_id,
                    user_id,
                    outcome_id,
                    booked,
                    note,
                    tag,
                    script_version,
                )
        assert row is not None
        return str(row["id"]), row["ghl_note_id"]

    async def finish(self, row_id: str, note_id: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE extension.call_outcomes SET ghl_note_id = $2 WHERE id = $1::uuid",
                row_id,
                note_id,
            )
