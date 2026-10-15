from pathlib import Path

import asyncpg

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
MIGRATION_LOCK = 0x57434D455854


async def run_migrations(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock($1::bigint)", MIGRATION_LOCK)
        await conn.execute("CREATE SCHEMA IF NOT EXISTS extension")
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS extension.schema_migrations ("
            "name TEXT PRIMARY KEY, "
            "applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        rows = await conn.fetch(
            "SELECT name FROM extension.schema_migrations ORDER BY name"
        )
        applied_names = {row["name"] for row in rows}
        for path in sorted(MIGRATIONS_DIR.glob("[0-9]" * 14 + "_*.sql")):
            if path.name in applied_names:
                continue
            await conn.execute(path.read_text())
            await conn.execute(
                "INSERT INTO extension.schema_migrations (name) VALUES ($1)",
                path.name,
            )
