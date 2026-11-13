import asyncio
from typing import Any

import pytest

from app.services import audit_runner
from app.services.audit_runner import _Trace

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class Repo:
    """Stores what add_trace is given; `drop` lists (step, status) writes that fail once."""

    def __init__(self, drop: set[tuple[str, str]] | None = None) -> None:
        self.events: list[dict[str, Any]] = []
        self.drop = drop or set()

    async def add_trace(self, _audit_id: str, event: dict[str, Any]) -> None:
        key = (event["id"], event["status"])
        if key in self.drop:
            self.drop.discard(key)
            raise TimeoutError("db slow")
        self.events.append(event)

    def folded(self) -> dict[str, str]:
        """What the panel shows: the last event of each step."""
        return {e["id"]: e["status"] for e in self.events}


async def test_a_dropped_done_is_written_again_so_the_step_is_not_left_running():
    repo = Repo(drop={("crawl", "done")})
    trace = _Trace(repo, "a1")  # type: ignore[arg-type]
    await trace.report("crawl", "running")
    await trace.report("crawl", "done", pages=9)  # this write is lost
    assert repo.folded() == {"crawl": "running"}  # what the panel would show for ever
    await trace.flush()
    assert repo.folded() == {"crawl": "done"}
    assert repo.events[-1]["detail"] == {"pages": 9}


async def test_a_later_event_of_a_step_replaces_the_one_that_was_lost():
    repo = Repo(drop={("psi", "running")})
    trace = _Trace(repo, "a1")  # type: ignore[arg-type]
    await trace.report("psi", "running")  # lost
    await trace.report("psi", "done")  # written
    await trace.flush()
    assert [e["status"] for e in repo.events] == [
        "done"
    ]  # "running" is not written late


async def test_a_step_that_never_reported_its_end_is_closed_as_failed():
    repo = Repo()
    trace = _Trace(repo, "a1")  # type: ignore[arg-type]
    await trace.report("onpage", "running")
    await trace.flush()
    assert repo.folded() == {"onpage": "failed"}
    assert repo.events[-1]["detail"]["error"] == "The step did not finish"


async def test_a_write_that_keeps_failing_never_stops_the_audit(monkeypatch):
    class Down:
        async def add_trace(self, *_a: Any) -> None:
            raise ConnectionError("db down")

    monkeypatch.setattr(audit_runner, "TRACE_WRITE_S", 0.01)
    monkeypatch.setattr(audit_runner, "TRACE_FLUSH_S", 0.01)
    trace = _Trace(Down(), "a1")  # type: ignore[arg-type]
    await trace.report("home", "running")
    await trace.report("home", "done")
    await asyncio.wait_for(trace.flush(), 1)  # returns; nothing raised
