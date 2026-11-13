"""Refresh-token rotation, with a small in-memory stand-in for the one table row."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest

from app.repositories import auth_session_repository as repo_mod
from app.repositories.auth_session_repository import AuthSessionRepository, token_hash

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class Row(dict):
    pass


class Conn:
    """Answers only the two statements rotate() sends."""

    def __init__(self, row: Row) -> None:
        self.row = row

    @asynccontextmanager
    async def transaction(self):
        yield

    async def fetchrow(self, _sql: str, presented: str) -> Row | None:
        r = self.row
        if (
            presented in (r["refresh_hash"], r["prev_refresh_hash"])
            and r["refresh_expires_at"] > datetime.now(UTC)
            and r["revoked_at"] is None
        ):
            return r
        return None

    async def execute(
        self, _sql: str, access, refresh, a_exp, r_exp, prev, until, _id
    ) -> None:
        self.row.update(
            access_hash=access,
            refresh_hash=refresh,
            access_expires_at=a_exp,
            refresh_expires_at=r_exp,
            prev_refresh_hash=prev,
            prev_refresh_until=until,
        )


class Pool:
    def __init__(self, conn: Conn) -> None:
        self.conn = conn

    @asynccontextmanager
    async def acquire(self):
        yield self.conn


def session(refresh: str) -> Row:
    return Row(
        id=1,
        user_id="u1",
        refresh_hash=token_hash(refresh),
        prev_refresh_hash=None,
        prev_refresh_until=None,
        refresh_expires_at=datetime.now(UTC) + timedelta(days=30),
        revoked_at=None,
    )


def repo(row: Row) -> AuthSessionRepository:
    return AuthSessionRepository(Pool(Conn(row)))  # type: ignore[arg-type]


async def test_a_lost_answer_can_be_asked_for_again_within_the_grace_window():
    row = session("wcm_rt_old")
    r = repo(row)
    first = await r.rotate(
        "wcm_rt_old"
    )  # the answer carrying `first` never reaches the client
    assert first is not None
    again = await r.rotate("wcm_rt_old")  # the client still holds the old token
    assert again is not None and again[2] != first[2]  # a fresh pair, not the lost one
    assert await r.rotate(again[2]) is not None  # and the new pair keeps working
    # the window was not extended by asking again: it still ends where the first rotation set it
    assert row["prev_refresh_until"] - datetime.now(UTC) <= repo_mod.REFRESH_GRACE


async def test_an_old_token_stops_working_after_the_grace_window():
    row = session("wcm_rt_old")
    r = repo(row)
    assert await r.rotate("wcm_rt_old") is not None
    row["prev_refresh_until"] = datetime.now(UTC) - timedelta(seconds=1)  # window over
    assert await r.rotate("wcm_rt_old") is None  # a stale or stolen token is refused


async def test_a_revoked_or_expired_session_never_rotates_even_in_the_window():
    for change in (
        {"revoked_at": datetime.now(UTC)},
        {"refresh_expires_at": datetime.now(UTC)},
    ):
        row = session("wcm_rt_old")
        r = repo(row)
        assert await r.rotate("wcm_rt_old") is not None
        row.update(change)
        assert await r.rotate("wcm_rt_old") is None
        assert await r.rotate("wcm_rt_unknown") is None
