import asyncio
from pathlib import Path
from typing import Any

import pytest

from app.core import migrate


class AsyncContext:
    def __init__(self, value: Any) -> None:
        self.value = value

    async def __aenter__(self) -> Any:
        return self.value

    async def __aexit__(self, *_args: object) -> None:
        return None


class FakeConnection:
    def __init__(self) -> None:
        self.applied: set[str] = set()
        self.statements: list[str] = []

    def transaction(self) -> AsyncContext:
        return AsyncContext(self)

    async def execute(self, query: str, *args: object) -> None:
        if query.startswith("INSERT INTO extension.schema_migrations"):
            self.applied.add(str(args[0]))
        elif query.startswith("SELECT ") and query.endswith(";"):
            self.statements.append(query)

    async def fetch(self, _query: str) -> list[dict[str, str]]:
        return [{"name": name} for name in self.applied]


class FakePool:
    def __init__(self, conn: FakeConnection) -> None:
        self.conn = conn

    def acquire(self) -> AsyncContext:
        return AsyncContext(self.conn)


def test_migrations_run_once_in_filename_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "20261015000002_second.sql").write_text("SELECT 2;")
    (tmp_path / "20261015000001_first.sql").write_text("SELECT 1;")
    monkeypatch.setattr(migrate, "MIGRATIONS_DIR", tmp_path)
    conn = FakeConnection()
    pool = FakePool(conn)

    asyncio.run(migrate.run_migrations(pool))  # type: ignore[arg-type]
    asyncio.run(migrate.run_migrations(pool))  # type: ignore[arg-type]

    assert conn.statements == ["SELECT 1;", "SELECT 2;"]
    assert conn.applied == {
        "20261015000001_first.sql",
        "20261015000002_second.sql",
    }
