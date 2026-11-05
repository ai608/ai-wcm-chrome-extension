from contextvars import ContextVar
from typing import Any

_LOG: ContextVar[dict[str, dict[str, Any]] | None] = ContextVar(
    "audit_fetch_log", default=None
)
MAX_ENTRIES = 500  # a runaway crawl can not grow this without bound


def bind() -> dict[str, dict[str, Any]]:
    log: dict[str, dict[str, Any]] = {}
    _LOG.set(log)
    return log


def snapshot() -> dict[str, dict[str, Any]]:
    """A copy of what has been recorded so far (empty when no audit is bound)."""
    return dict(_LOG.get() or {})


def record(requested: str, **info: Any) -> None:
    log = _LOG.get()
    if log is not None and (requested in log or len(log) < MAX_ENTRIES):
        log[requested] = info
